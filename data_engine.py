import struct
import xml.etree.ElementTree as ET
import io
from models import XDFMap

class DataEngine:
    @staticmethod
    def read_raw(data, addr, is16, signed):
        if not data or addr < 0 or addr + (2 if is16 else 1) > len(data):
            return 0
        # h/b pro signed, H/B pro unsigned
        fmt = f"<{'h' if signed else 'H'}" if is16 else f"<{'b' if signed else 'B'}"
        return struct.unpack_from(fmt, data, addr)[0]

    @staticmethod
    def scan_for_matches(src_data, target_data, addr, rows, cols, is16, max_matches=100):
        """
        Hledá výskyty vzoru v cílových datech s limitem pro úsporu paměti.
        """
        matches = []
        if addr < 0 or not src_data or not target_data:
            return matches
            
        # Velikost dat mapy (zahrnuje rows * cols)
        # Omezení size na 64 bytů bylo v původním kódu, možná kvůli rychlosti nebo specifikům?
        # Pro přesnost bychom měli vzít celou mapu, ale u velkých map to může být pomalé.
        # Zachovám zatím logiku "patternu", ale je lepší vzít o něco víc než nic.
        # Pokud je mapa malá (např. 1x1), vezmeme ji celou.
        element_size = 2 if is16 else 1
        total_size = rows * cols * element_size
        
        # Pokud je mapa obrovská, hledat podle celého obsahu je nejbezpečnější pro unikátnost.
        # Původní kód měl `min(..., 64)`. Pro malé mapy (KRKTE) je klíčové vzít vše.
        # Pro velké mapy je 64 bajtů obvykle dost na unikátnost, ale nemusí být.
        # Zkusíme vzít celou mapu, pokud není extrémně velká (> 256b), jinak ořízneme?
        # Pro "100% jistotu" je lepší vzít celou mapu.
        
        pattern_size = total_size
        if addr + pattern_size > len(src_data):
            return matches # Out of bounds ve zdrojových datech
            
        pattern = src_data[addr : addr + pattern_size]
        
        # Hledání všech výskytů
        start = 0
        while len(matches) < max_matches:
            idx = target_data.find(pattern, start)
            if idx == -1:
                break
            matches.append(idx)
            start = idx + 1 # Posunout se o 1 byte dál a hledat znovu
            
        return matches

    def resolve_matches(self, all_maps, src_data, trg_data):
        """
        Analyzuje nalezené shody a řeší duplicity (Sequential Matching).
        Nastavuje match_type (UNIQUE, SEQUENTIAL, AMBIGUOUS, ERROR).
        Řeší také osy (pokud nejsou nalezeny, označí je).
        """
        # 1. Seskupení map podle obsahu (patternu) ve zdrojových datech
        # Key: bytes (pattern), Value: list of XDFMap
        pattern_groups = {}
        
        for m in all_maps.values():
            if m.z_addr <= 0 or m.z_addr >= len(src_data):
                m.match_type = "ERROR"
                continue
                
            size = m.z_rows * m.z_cols * (2 if m.z_is16 else 1)
            pattern = src_data[m.z_addr : m.z_addr + size]
            
            if pattern not in pattern_groups:
                pattern_groups[pattern] = []
            pattern_groups[pattern].append(m)

        # 2. Vyhodnocení skupin
        for pattern, maps in pattern_groups.items():
            # Najdeme všechny výskyty tohoto patternu v cílových datech
            # (To už jsme teoreticky udělali pro každou mapu zvlášť, ale `matches` 
            # by měly být stejné pro všechny mapy se stejným patternem).
            # Vezmeme matches z první mapy (předpoklad: sken proběhl)
            if not maps: continue
            
            matches = maps[0].matches
            match_count = len(matches)
            
            if match_count == 0:
                for m in maps: m.match_type = "NONE"
                continue
            
            # UNIQUE MATCH
            if len(maps) == 1 and match_count == 1:
                m = maps[0]
                m.match_type = "UNIQUE"
                m.target_addr = matches[0]
                m.match_percent = 100
                continue
                
            # SEQUENTIAL MATCH (Paradox duplicit)
            # Pokud máme N map se stejným obsahem a N nalezených výskytů
            if len(maps) == match_count and match_count > 1:
                # Seřadíme mapy podle původní adresy
                sorted_maps = sorted(maps, key=lambda x: x.z_addr)
                # Seřadíme nálezy (jsou už seřazené z scan_for_matches, ale pro jistotu)
                sorted_matches = sorted(matches)
                
                for i, m in enumerate(sorted_maps):
                    m.match_type = "SEQUENTIAL"
                    m.target_addr = sorted_matches[i]
                    m.match_percent = 100 # S určitou mírou nejistoty, ale pro export OK
                continue
                
            # AMBIGUOUS (Nesedí počty)
            for m in maps:
                m.match_type = "AMBIGUOUS"
                m.match_percent = 0

        # 3. Dořešení OS (po vyřešení adres Z)
        for m in all_maps.values():
            if m.match_type not in ["UNIQUE", "SEQUENTIAL"]:
                continue
                
            # Posun (offset) oproti původní adrese
            offset = m.target_addr - m.z_addr
            
            # Funkce pro kontrolu osy
            def check_axis(ax_addr, ax_is16, matches_list):
                if ax_addr == 0: return -1 # Osa není definovaná (nebo internal)
                
                # Zkusíme najít osu se stejným posunem (ideal case)
                # Nebo hledáme pattern osy a doufáme v unikátnost
                
                # Logika:
                # 1. Zkusit aplikovat offset z mapy? (Často osy leží jinde a mají jiný offset)
                # -> NE, osy jsou často sdílené. Musíme je hledat nezávisle.
                # Ale my už skenovali? Ne, scan_for_matches v main.py jel jen pro Z.
                # Musíme oskenovat i osy, pokud nejsou v `matches_list`.
                # (V main.py to ještě není, přidáme to tam nebo sem? Lepší sem, pokud máme data).
                
                # Zde provedeme "Lazy scan" pro osy, pokud nemáme výsledky
                # Ale `src_data` a `trg_data` máme.
                
                # Velikost osy? XDFMap má x_count/y_count.
                # Count * element_size
                pass 
                
            # Pro tuto fázi implementujeme jednoduchý scan os uvnitř resolve_matches
            # Nebo spoléháme, že už je naplněno? Zatím není. Uděláme to tady.
            
            # --- Check X Axis ---
            if m.x_addr > 0:
                matches = self.scan_for_matches(src_data, trg_data, m.x_addr, 1, m.x_count, m.x_is16)
                m.x_matches = matches
                
                if matches:
                    if len(matches) == 1:
                        m.target_x_addr = matches[0]
                        m.x_match_type = "UNIQUE"
                    else:
                        map_offset = m.target_addr - m.z_addr
                        if (m.x_addr + map_offset) in matches:
                            m.target_x_addr = m.x_addr + map_offset
                            m.x_match_type = "OFFSET"
                        else:
                            m.target_x_addr = matches[0]
                            m.x_match_type = "GUESS"
                else:
                    m.target_x_addr = -1
                    m.x_match_type = "NONE"
            
            # --- Check Y Axis ---
            if m.y_addr > 0:
                matches = self.scan_for_matches(src_data, trg_data, m.y_addr, 1, m.y_count, m.y_is16)
                m.y_matches = matches
                
                if matches:
                    if len(matches) == 1:
                        m.target_y_addr = matches[0]
                        m.y_match_type = "UNIQUE"
                    else:
                        map_offset = m.target_addr - m.z_addr
                        if (m.y_addr + map_offset) in matches:
                            m.target_y_addr = m.y_addr + map_offset
                            m.y_match_type = "OFFSET"
                        else:
                            m.target_y_addr = matches[0]
                            m.y_match_type = "GUESS"
                else:
                    m.target_y_addr = -1
                    m.y_match_type = "NONE"


    def write_xdf(self, original_tree, all_maps, output_path):
        """
        Zapíše nové XDF obsahující pouze mapy typu UNIQUE nebo SEQUENTIAL.
        Vkládá příznak (?) do názvu u nejistých shod.
        """
        root = original_tree.getroot()
        nodes_to_keep = set(m.node for m in all_maps.values() if m.match_type in ["UNIQUE", "SEQUENTIAL"])
        
        # 1. Aktualizace adres a NÁZVŮ u zachovaných map
        for m in all_maps.values():
            if m.node in nodes_to_keep:
                # Titulek mapy - synchronizace značek s GUI
                title_node = m.node.find("title")
                if title_node is not None:
                    # Odstraníme staré značky (vše za první závorkou se značkou)
                    orig_text = str(title_node.text or "")
                    clean_title = orig_text
                    for marker_start in [" (?", " (x-off", " (y-off"]:
                        if marker_start in clean_title:
                            clean_title = clean_title.split(marker_start)[0]
                    clean_title = clean_title.strip()
                    
                    markers = ""
                    if m.match_type == "SEQUENTIAL": markers += " (seq)"
                    
                    # Osa X markers
                    if m.x_match_type == "OFFSET": markers += " (x-off)"
                    elif m.x_match_type == "GUESS": markers += " (?x)"
                    
                    # Osa Y markers
                    if m.y_match_type == "OFFSET": markers += " (y-off)"
                    elif m.y_match_type == "GUESS": markers += " (?y)"
                    
                    # Výsledek: Pouze pokud jsou nějaké markers a není to UNIQUE mapa s UNIQUE osami
                    if markers:
                        title_node.text = clean_title + markers
                    else:
                        title_node.text = clean_title

                # Z
                if m.is_scalar:
                     emb = m.node.find("EMBEDDEDDATA")
                     if emb is not None: emb.set('mmedaddress', f"0x{m.target_addr:X}")
                else:
                    z_axis = m.node.find(".//XDFAXIS[@id='z']")
                    if z_axis is not None:
                        emb = z_axis.find("EMBEDDEDDATA")
                        if emb is not None: emb.set('mmedaddress', f"0x{m.target_addr:X}")
                        
                    # Osy
                    for ax_id, target_ax_addr in [('x', m.target_x_addr), ('y', m.target_y_addr)]:
                        ax_node = m.node.find(f".//XDFAXIS[@id='{ax_id}']")
                        if ax_node is not None:
                            if target_ax_addr > 0:
                                emb = ax_node.find("EMBEDDEDDATA")
                                if emb is not None: emb.set('mmedaddress', f"0x{target_ax_addr:X}")
                            else:
                                # Fallback pro nenalezenou osu - nastavit na 0x0
                                emb = ax_node.find("EMBEDDEDDATA")
                                if emb is not None: emb.set('mmedaddress', "0x0")
        
        # 2. Rekurzivní mazání nechtěných map
        # Musíme najít rodiče každého nodu, abychom ho mohli smazat
        parent_map = {c: p for p in root.iter() for c in p}
        
        for tag in ['XDFTABLE', 'XDFCONSTANT']:
            for node in list(root.iter(tag)):
                if node not in nodes_to_keep:
                    parent = parent_map.get(node)
                    if parent is not None:
                        parent.remove(node)
        
        original_tree.write(output_path, encoding="cp1252", xml_declaration=True)

    def parse_xdf(self, path):
        content = open(path, 'rb').read().decode('cp1252', errors='ignore')
        tree = ET.parse(io.StringIO(content))
        all_maps = {}
        
        #iter() pro rekurzivní vyhledávání v celém stromu (včetně kategorií)
        for tag in ['XDFTABLE', 'XDFCONSTANT']:
            for node in tree.getroot().iter(tag):
                title = node.findtext('title', 'Unknown')
                m = XDFMap(title, node, is_scalar=(tag == 'XDFCONSTANT'))
                
                def parse_emb(emb_node):
                    if emb_node is None: return 0, False, False
                    addr = int(emb_node.get('mmedaddress', '0x0'), 16)
                    is16 = emb_node.get('mmedelementsizebits') == "16"
                    flags = emb_node.get('mmedtypeflags', '0x00')
                    is_signed = (flags == "0x01")
                    return addr, is16, is_signed

                if m.is_scalar:
                    emb = node.find("EMBEDDEDDATA")
                    m.z_addr, m.z_is16, m.z_signed = parse_emb(emb)
                    math_node = node.find("MATH")
                    m.z_eq = math_node.get('equation', 'X') if math_node is not None else "X"
                else:
                    for ax_id in ['x', 'y', 'z']:
                        ax_node = node.find(f".//XDFAXIS[@id='{ax_id}']")
                        if ax_node is None: continue
                        emb = ax_node.find("EMBEDDEDDATA")
                        addr, is16, signed = parse_emb(emb)
                        math_node = ax_node.find("MATH")
                        eq = math_node.get('equation', 'X') if math_node is not None else "X"
                        
                        if ax_id == 'z':
                            m.z_addr, m.z_is16, m.z_signed, m.z_eq = addr, is16, signed, eq
                            m.z_rows = int(emb.get('mmedrowcount', '1')) if emb is not None else 1
                            m.z_cols = int(emb.get('mmedcolcount', '1')) if emb is not None else 1
                        elif ax_id == 'x':
                            m.x_addr, m.x_is16, m.x_signed, m.x_eq = addr, is16, signed, eq
                            m.x_count = int(ax_node.findtext('indexcount', '1'))
                        elif ax_id == 'y':
                            m.y_addr, m.y_is16, m.y_signed, m.y_eq = addr, is16, signed, eq
                            m.y_count = int(ax_node.findtext('indexcount', '1'))
                
                all_maps[title] = m
        return tree, all_maps
