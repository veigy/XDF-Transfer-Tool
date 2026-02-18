import struct
import xml.etree.ElementTree as ET
import io
from models import XDFMap

class DataEngine:
    @staticmethod
    def read_raw(data, addr, is16, signed=False):
        """
        Reads raw value from BIN.
        Always returns unsigned; calculate() handles the rest.
        """
        if not data or addr < 0 or addr + (2 if is16 else 1) > len(data):
            return 0
        fmt = "<H" if is16 else "<B"
        return struct.unpack_from(fmt, data, addr)[0]

    @staticmethod
    def scan_for_matches(src_data, target_data, addr, rows, cols, is16, max_matches=100):
        matches = []
        if addr < 0 or not src_data or not target_data:
            return matches
        element_size = 2 if is16 else 1
        total_size = rows * cols * element_size
        if addr + total_size > len(src_data): return matches
        pattern = src_data[addr : addr + total_size]
        start = 0x10000 # Ignore Segment 0 (Bootloader/RAM)
        while len(matches) < max_matches:
            idx = target_data.find(pattern, start)
            if idx == -1: break
            matches.append(idx)
            start = idx + 1
        return matches

    def scan_with_context(self, src_data, target_data, addr, rows, cols, is16):
        """
        Returns: (matches, is_deep, radius_l, radius_r)
        """
        matches = self.scan_for_matches(src_data, target_data, addr, rows, cols, is16)
        if len(matches) == 1:
            return matches, False, 0, 0 # Standard Unique (Radius 0)
        if len(matches) == 0:
            return matches, False, 0, 0
            
        element_size = 2 if is16 else 1
        ps = rows * cols * element_size
        radius_l = radius_r = 0
        current_matches = matches[:]
        
        # LEFT
        for step in range(1, 9):
            if addr - step < 0: break
            radius_l = step
            src_left = src_data[addr - step : addr]
            filtered = [m for m in current_matches if m - step >= 0 and target_data[m - step : m] == src_left]
            if len(filtered) == 1: return filtered, True, radius_l, 0
            if len(filtered) == 0:
                radius_l -= 1
                break 
            current_matches = filtered

        # RIGHT
        for step in range(1, 9):
            if addr + ps + step > len(src_data): break
            radius_r = step
            src_right = src_data[addr + ps : addr + ps + step]
            filtered = [m for m in current_matches if m + ps + step <= len(target_data) and target_data[m + ps : m + ps + step] == src_right]
            if len(filtered) == 1: return filtered, True, radius_l, radius_r
            if len(filtered) == 0:
                radius_r -= 1
                break
            current_matches = filtered
        return current_matches, (len(current_matches) < len(matches)), radius_l, radius_r

    def resolve_matches(self, all_maps, src_data, trg_data):
        """
        Priority: 1. Standard Unique, 2. Deep Match Unique, 3. Sequential/Offset.
        """
        # 1. First verify all maps using scan with context
        pattern_groups = {}
        for m in all_maps.values():
            if m.z_addr <= 0: continue
            
            # If hloubkově unique (Standard or Deep), confirm immediately
            if m.match_count == 1:
                # Standard unique (is_deep will be False from ScanWorker if this method was used earlier)
                m.match_type = "UNIQUE"
                m.target_addr = m.matches[0]
                m.match_percent = 100
                continue
            
            # If not unique, group for sequential analysis
            size = m.z_rows * m.z_cols * (2 if m.z_is16 else 1)
            if m.z_addr + size > len(src_data): continue
            pattern = src_data[m.z_addr : m.z_addr + size]
            if pattern not in pattern_groups: pattern_groups[pattern] = []
            pattern_groups[pattern].append(m)

        # 2. Group evaluation (Sequential matching with Deep protection)
        for pattern, maps in pattern_groups.items():
            # Before doing sequence, try Deep Match again for each map (only for this group)
            unresolved = []
            for m in maps:
                if m.is_deep and len(m.matches) == 1:
                    m.match_type = "UNIQUE"
                    m.target_addr = m.matches[0]
                    m.match_percent = 100
                    # Confirmed via context, excluded from sequence
                else:
                    unresolved.append(m)
            
            if not unresolved: continue
            
            # Remaining maps in pattern are resolved sequentially
            # But must exclude matches (addresses in target) already occupied by Deep maps!
            occupied_addresses = set(m.target_addr for m in maps if m.match_type == "UNIQUE")
            available_matches = [addr for addr in maps[0].matches if addr not in occupied_addresses]
            
            if len(unresolved) == len(available_matches) and len(available_matches) > 0:
                sorted_maps = sorted(unresolved, key=lambda x: x.z_addr)
                sorted_matches = sorted(available_matches)
                for i, m in enumerate(sorted_maps):
                    m.match_type = "SEQUENTIAL"
                    m.target_addr = sorted_matches[i]
                    m.match_percent = 100
            else:
                for m in unresolved:
                    m.match_type = "AMBIGUOUS"
                    m.match_percent = 0

        # 3. Axis resolution - now also with DEEP LOGIC
        for m in all_maps.values():
            if m.target_addr <= 0: continue
            
            for ax in ['x', 'y']:
                addr = getattr(m, f"{ax}_addr")
                count = getattr(m, f"{ax}_count")
                is16 = getattr(m, f"{ax}_is16")
                if addr <= 0: continue
                
                # Deep Match for axis
                matches, is_deep, rl, rr = self.scan_with_context(src_data, trg_data, addr, 1, count, is16)
                setattr(m, f"{ax}_matches", matches)
                setattr(m, f"{ax}_is_deep", is_deep)
                setattr(m, f"{ax}_deep_l", rl)
                setattr(m, f"{ax}_deep_r", rr)
                
                if len(matches) == 1:
                    setattr(m, f"target_{ax}_addr", matches[0])
                    setattr(m, f"{ax}_match_type", "UNIQUE")
                elif matches:
                    # If not unique, try OFFSET
                    offset = m.target_addr - m.z_addr
                    if (addr + offset) in matches:
                        setattr(m, f"target_{ax}_addr", addr + offset)
                        setattr(m, f"{ax}_match_type", "OFFSET")
                    else:
                        setattr(m, f"target_{ax}_addr", matches[0])
                        setattr(m, f"{ax}_match_type", "GUESS")
                else:
                    setattr(m, f"target_{ax}_addr", -1)
                    setattr(m, f"{ax}_match_type", "NONE")

    def write_xdf(self, original_tree, all_maps, output_path, include_deep=True):
        root = original_tree.getroot()
        def should_export(m):
            if m.match_type not in ["UNIQUE", "SEQUENTIAL", "FUZZY"]: return False
            if m.is_deep and not include_deep: return False
            return True
        nodes_to_keep = set(m.node for m in all_maps.values() if should_export(m))
        for m in all_maps.values():
            if m.node in nodes_to_keep:
                title_node = m.node.find("title")
                if title_node is not None:
                    text = str(title_node.text or "")
                    for marker in [" (seq)", " (deep)", " (x-deep)", " (y-deep)", " (x-off)", " (y-off)", " (?x)", " (?y)"]:
                        if marker in text: text = text.replace(marker, "")
                    markers = ""
                    if m.match_type == "SEQUENTIAL": markers += " (seq)"
                    if m.match_type == "FUZZY": markers += " (fuzzy)"
                    if m.is_deep: markers += " (deep)"
                    if m.x_is_deep: markers += " (x-deep)"
                    if m.y_is_deep: markers += " (y-deep)"
                    title_node.text = text.strip() + markers
                if m.is_scalar:
                    emb = m.node.find("EMBEDDEDDATA")
                    if emb is not None: emb.set('mmedaddress', f"0x{m.target_addr:X}")
                else:
                    z_axis = m.node.find(".//XDFAXIS[@id='z']")
                    if z_axis is not None:
                        emb = z_axis.find("EMBEDDEDDATA")
                        if emb is not None: emb.set('mmedaddress', f"0x{m.target_addr:X}")
                    for ax_id, addr in [('x', m.target_x_addr), ('y', m.target_y_addr)]:
                        # Case-insensitive axis search using id attribute
                        ax_node = None
                        for axis in m.node.findall(".//XDFAXIS"):
                            if axis.get('id', '').lower() == ax_id.lower():
                                ax_node = axis
                                break
                        
                        if ax_node is not None:
                            emb = ax_node.find("EMBEDDEDDATA")
                            if emb is not None: emb.set('mmedaddress', f"0x{addr:X}" if addr > 0 else "0x0")
                            
                            # Deep markers for axes
                            is_deep = getattr(m, f"{ax_id}_is_deep", False)
                            if is_deep:
                                ax_title_node = ax_node.find("title")
                                if ax_title_node is not None:
                                    ax_text = str(ax_title_node.text or "")
                                    marker = f" ({ax_id}-deep)"
                                    if marker not in ax_text:
                                        ax_title_node.text = ax_text.strip() + marker
                                    
                                    # Write to title attribute as well (some editors read from there)
                                    attr_title = ax_node.get('title')
                                    if attr_title and marker not in str(attr_title):
                                        ax_node.set('title', str(attr_title).strip() + marker)
        parent_map = {c: p for p in root.iter() for c in p}
        for tag in ['XDFTABLE', 'XDFCONSTANT']:
            for node in list(root.iter(tag)):
                if node not in nodes_to_keep:
                    parent = parent_map.get(node)
                    if parent is not None: parent.remove(node)
        original_tree.write(output_path, encoding="cp1252", xml_declaration=True)

    def parse_xdf(self, path):
        content = open(path, 'rb').read().decode('cp1252', errors='ignore')
        tree = ET.parse(io.StringIO(content))
        all_maps = {}
        
        def _find(parent, tag):
            if parent is None: return None
            res = parent.find(tag)
            if res is not None: return res
            tag_u = tag.upper()
            for child in parent:
                if child.tag.upper() == tag_u: return child
            return None

        def _p(n):
            if n is None: return 0, False, False
            a = int(n.get('mmedaddress', '0x0'), 16)
            i = n.get('mmedelementsizebits') == "16"
            try:
                flags = int(n.get('mmedtypeflags', '0x00'), 16)
                s = bool(flags & 0x01)
            except: s = False
            return a, i, s

        def _get_eq(math_node, axis_node=None):
            base_eq = "X"
            if math_node is not None:
                base_eq = math_node.get('equation', 'X')
            
            # kmul/kadd can be in MATH tag or directly in XDFAXIS/XDFTABLE (axis_node)
            src = math_node if math_node is not None else axis_node
            if src is None: return base_eq
            
            kmul = src.get('kmul') or (axis_node.get('kmul') if axis_node is not None and axis_node != src else None) or '1.0'
            kadd = src.get('kadd') or (axis_node.get('kadd') if axis_node is not None and axis_node != src else None) or '0.0'
            
            try:
                f_mul = float(kmul)
                f_add = float(kadd)
                if f_mul != 1.0 or f_add != 0.0:
                    return f"({base_eq})*{f_mul} + {f_add}"
            except:
                pass
            return base_eq

        for tag in ['XDFTABLE', 'XDFCONSTANT']:
            for node in tree.getroot().iter(tag):
                title = node.findtext('title', 'Unknown')
                m = XDFMap(title, node, is_scalar=(tag == 'XDFCONSTANT'))
                
                if m.is_scalar:
                    m.z_addr, m.z_is16, m.z_signed = _p(_find(node, "EMBEDDEDDATA"))
                    m.z_eq = _get_eq(_find(node, "MATH"), node)
                else:
                    for aid in ['x', 'y', 'z']:
                        n = None
                        for cand in node.findall(".//XDFAXIS"):
                            if cand.get('id', '').lower() == aid: n = cand; break
                        if n is None: continue
                        e = _find(n, "EMBEDDEDDATA"); a, i, s = _p(e)
                        eq = _get_eq(_find(n, "MATH"), n)
                        if aid == 'z':
                            m.z_addr, m.z_is16, m.z_signed, m.z_eq = a, i, s, eq
                            m.z_rows = int(e.get('mmedrowcount', '1')) if e is not None else 1
                            m.z_cols = int(e.get('mmedcolcount', '1')) if e is not None else 1
                        elif aid == 'x':
                            m.x_addr, m.x_is16, m.x_signed, m.x_eq = a, i, s, eq
                            m.x_count = int(n.findtext('indexcount', '1') or '1')
                        elif aid == 'y':
                            m.y_addr, m.y_is16, m.y_signed, m.y_eq = a, i, s, eq
                            m.y_count = int(n.findtext('indexcount', '1') or '1')
                all_maps[title] = m
        return tree, all_maps

    def scan_fuzzy_sequential(self, all_maps, src_data, target_data, progress_callback=None):
        """
        Attempts to find missing maps (NONE) in gaps between already found ones (UNIQUE/SEQ/DEEP).
        Uses +/- 8 tolerance for each byte and at least 85% area match.
        """
        # 1. Collect anchors (already found maps) including their size
        anchors = []
        for m in all_maps.values():
            if m.match_type in ["UNIQUE", "SEQUENTIAL", "DEEP"] and m.target_addr != -1:
                element_size = 2 if m.z_is16 else 1
                size = m.z_rows * m.z_cols * element_size
                anchors.append((m.z_addr, m.target_addr, size))
        
        # Sort by source address
        anchors.sort(key=lambda x: x[0])
        
        # 2. Iterate through missing maps
        missing_maps = sorted([m for m in all_maps.values() if m.match_type == "NONE"], key=lambda x: x.z_addr)
        total_missing = len(missing_maps)
        if total_missing == 0: return

        for i, m in enumerate(missing_maps):
            if progress_callback:
                progress_callback(int((i / total_missing) * 100))
            
            element_size = 2 if m.z_is16 else 1
            size = m.z_rows * m.z_cols * element_size
            if m.z_addr + size > len(src_data): continue
            pattern = src_data[m.z_addr : m.z_addr + size]
            
            # Najdeme okno mezi kotvami
            src_addr = m.z_addr
            prev_anchor = None
            for a in anchors:
                if a[0] < src_addr: prev_anchor = a
                else: break
            
            next_anchor = None
            for a in anchors:
                if a[0] > src_addr:
                    next_anchor = a
                    break
            
            # Search start is after the end of the previous map
            start_search = (prev_anchor[1] + prev_anchor[2]) if prev_anchor else 0x10000
            # Search end is the start of the next map
            end_search = next_anchor[1] if next_anchor else len(target_data)
            
            # If window is too small, try to expand it slightly (preventing sorting errors)
            if start_search >= end_search:
                # Emergency expansion of 8KB if it is "tight"
                start_search = max(0, start_search - 8192)
                end_search = min(len(target_data), end_search + 8192)

            if start_search >= end_search: continue
            
            fuzzy_addr = self.find_fuzzy_match(target_data, start_search, end_search, pattern, tolerance=10, threshold=0.80)
            
            if fuzzy_addr != -1:
                m.match_type = "FUZZY"
                m.target_addr = fuzzy_addr
                m.matches = [fuzzy_addr]
                # New anchor
                anchors.append((m.z_addr, m.target_addr, size))
                anchors.sort(key=lambda x: x[0])
    
    def find_fuzzy_match(self, data, start, end, pattern, tolerance=8, threshold=0.85):
        """
        Searches for pattern in data[start:end] with tolerance and match threshold.
        """
        pat_len = len(pattern)
        if pat_len < 4: return -1 # Too small maps aren't searched fuzzy (false positives risk)
    
        window_size = end - start
        if window_size < pat_len: return -1
        
        mismatches_allowed = int(pat_len * (1.0 - threshold))
        
        for i in range(start, end - pat_len + 1):
            mismatches = 0
            match = True
            
            # Fast check of first and last byte (optimization)
            if abs(data[i] - pattern[0]) > tolerance and abs(data[i+pat_len-1] - pattern[pat_len-1]) > tolerance:
                if mismatches_allowed < 1: continue

            for j in range(pat_len):
                if abs(data[i+j] - pattern[j]) > tolerance:
                    mismatches += 1
                    if mismatches > mismatches_allowed:
                        match = False
                        break
            
            if match:
                return i
        return -1
