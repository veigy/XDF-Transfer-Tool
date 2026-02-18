import sys
import os
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QListWidget, QTableWidget, QPushButton, 
                             QFileDialog, QLabel, QLineEdit, QSplitter, QTabWidget, 
                             QProgressBar, QListWidgetItem, QCheckBox, QHeaderView, 
                             QTableWidgetItem)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QColor, QBrush, QIcon
from data_engine import DataEngine
from ui_components import UIManager

def resource_path(relative_path):
    """ Get absolute path to resources, works for PyInstaller EXE """
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

# Fix for Windows taskbar icon
if sys.platform == 'win32':
    import ctypes
    myappid = 'veigy.xdftransfertool.v100'
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)

class ScanWorker(QThread):
    progress_update = pyqtSignal(int)
    log_message = pyqtSignal(str)
    scanning_finished = pyqtSignal(int, int) # found, unique

    def __init__(self, engine, all_maps, bin_src, bin_trg):
        super().__init__()
        self.engine = engine
        self.all_maps = all_maps
        self.bin_src = bin_src
        self.bin_trg = bin_trg
        self._is_running = True

    def run(self):
        total = len(self.all_maps)
        if total == 0:
            self.scanning_finished.emit(0, 0)
            return

        # 1. Scan Z addresses (Data)
        for i, (name, m) in enumerate(self.all_maps.items()):
            if not self._is_running: break
            
            # Reset
            m.target_addr = -1
            m.match_count = 0
            m.matches = []
            m.match_type = "NONE"
            m.x_matches = []
            m.y_matches = []
            
            # Scan Z (Deep scanning with context)
            matches, is_deep, radius_l, radius_r = self.engine.scan_with_context(self.bin_src, self.bin_trg, m.z_addr, m.z_rows, m.z_cols, m.z_is16)
            m.matches = matches
            m.match_count = len(matches)
            m.is_deep = is_deep
            m.deep_l = radius_l
            m.deep_r = radius_r
            
            if i % 10 == 0:
                self.progress_update.emit(int((i / total) * 90)) # 0-90% for scanning

        # 2. Resolve Matches (Sequential logic + Axis scanning)
        self.log_message.emit("Analyzing duplicates and axes...")
        self.engine.resolve_matches(self.all_maps, self.bin_src, self.bin_trg)
        self.progress_update.emit(100)
        
        # 3. Count results
        found = 0
        unique = 0
        for m in self.all_maps.values():
            if m.match_type in ["UNIQUE", "SEQUENTIAL"]:
                found += 1
                if m.match_type == "UNIQUE":
                    unique += 1
        
        self.scanning_finished.emit(found, unique)

    def stop(self):
        self._is_running = False

class FuzzyScanWorker(QThread):
    progress_update = pyqtSignal(int)
    log_message = pyqtSignal(str)
    fuzzy_finished = pyqtSignal(int) # found_count

    def __init__(self, engine, all_maps, bin_src, bin_trg):
        super().__init__()
        self.engine = engine
        self.all_maps = all_maps
        self.bin_src = bin_src
        self.bin_trg = bin_trg
        self._is_running = True

    def run(self):
        # Starting fuzzy scan
        self.log_message.emit("Starting Fuzzy Search (searching with tolerance)...")
        self.engine.scan_fuzzy_sequential(self.all_maps, self.bin_src, self.bin_trg, self.progress_update.emit)
        
        # Count new finds (FUZZY)
        fuzzy_count = sum(1 for m in self.all_maps.values() if m.match_type == "FUZZY")
        self.fuzzy_finished.emit(fuzzy_count)

    def stop(self):
        self._is_running = False

class ME7TransferApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("XDF Transfer Tool v1.0")
        self.setWindowIcon(QIcon(resource_path("favicon.ico")))
        self.resize(1500, 900)
        
        # Module initialization
        self.engine = DataEngine()
        self.ui_man = UIManager()
        self.bin_src = self.bin_trg = self.xdf_tree = None
        self.src_filename = self.trg_filename = ""
        self.all_maps = {}
        self.worker = None

        # UI Assembly
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QHBoxLayout(main_widget)

        # Toolbar
        left_panel = QVBoxLayout()
        self.btn_load_xdf = QPushButton("1. Load XDF")
        self.btn_load_src = QPushButton("2. Load SOURCE BIN")
        self.btn_load_trg = QPushButton("3. Load TARGET BIN")
        
        self.progress = QProgressBar()
        self.progress.setValue(0)
        self.progress.setTextVisible(True)
        
        self.btn_export = QPushButton("4. EXPORT XDF")
        self.btn_export.setStyleSheet("background: #aa0000; color: white; font-weight: bold;")
        
        self.btn_fuzzy = QPushButton("Fuzzy Search (Experimental)")
        self.btn_fuzzy.setEnabled(False)
        self.btn_fuzzy.setStyleSheet("color: #FFA500; font-weight: bold;")

        self.cb_deep_export = QCheckBox("Include (deep) results in export")
        self.cb_deep_export.setChecked(True)
        self.cb_deep_export.setStyleSheet("color: #444; font-size: 11px;")
        
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search...")
        self.search.textChanged.connect(self.update_list)
        
        self.tabs = QTabWidget()
        self.table_map = QTableWidget(0, 2)
        self.table_scat = QTableWidget(0, 2)
        
        for t in [self.table_map, self.table_scat]:
            t.setHorizontalHeaderLabels(["Address", "Map Name"])
            t.setColumnWidth(0, 85)
            t.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
            t.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
            t.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
            t.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
            t.verticalHeader().setVisible(False)
            t.itemSelectionChanged.connect(self.select_map)

        self.tabs.addTab(self.table_map, "Maps")
        self.tabs.addTab(self.table_scat, "Scalars")
        
        self.lbl_info = QLabel("Status: Ready")
        self.lbl_info.setWordWrap(True)
        self.lbl_info.setMaximumWidth(280) # Zabrání roztahování panelu
        self.lbl_info.setStyleSheet("color: #fff; font-weight: bold; font-size: 11px; padding: 5px; background: rgba(255,255,255,5%); border-radius: 3px;")
        
        # Color Legend
        self.lbl_legend = QLabel(
            "<b>Results Legend:</b><br/>"
            "<font color='darkgreen'>● UNIQUE</font> - Unique (clear match)<br/>"
            "<font color='#006400'>● DEEP</font> - Confirmed via surrounding context<br/>"
            "<font color='#FF8C00'>● SEQ</font> - Sequential duplicate matching<br/>"
            "<font color='#DAA520'>● FUZZY</font> - Found with tolerance (check!)<br/>"
            "<font color='red'>● AMBIGUOUS</font> - Multiple possible locations<br/>"
            "<font color='#008000'><b>(x/y-off)</b></font> - Axis found via offset"
        )
        self.lbl_legend.setStyleSheet("""
            color: #eee; 
            background: rgba(255,255,255,5%); 
            border: 1px solid rgba(255,255,255,10%); 
            border-radius: 4px;
            padding: 8px; 
            font-size: 10px;
        """)
        
        # Layout components
        left_panel.addWidget(self.btn_load_xdf)
        left_panel.addWidget(self.btn_load_src)
        left_panel.addWidget(self.btn_load_trg)
        left_panel.addWidget(QLabel("Progress:"))
        left_panel.addWidget(self.progress)
        left_panel.addWidget(self.btn_export)
        left_panel.addWidget(self.btn_fuzzy)
        left_panel.addWidget(self.cb_deep_export)
        left_panel.addWidget(self.search)
        left_panel.addWidget(self.tabs)
        left_panel.addWidget(self.lbl_info)
        left_panel.addSpacing(10)
        left_panel.addWidget(self.lbl_legend)

        # Tables - wrapped in layout with stretch at bottom to prevent small maps from being stretched
        right_panel = QVBoxLayout()
        self.splitter = QSplitter(Qt.Orientation.Vertical)
        self.splitter.setHandleWidth(2) # Narrower gap between tables
        self.table_src = QTableWidget(); self.table_trg = QTableWidget()
        self.splitter_spacer = QWidget() # Pružina pro horizontální režim
        
        # Scroll synchronization
        self.table_src.verticalScrollBar().valueChanged.connect(self.table_trg.verticalScrollBar().setValue)
        self.table_trg.verticalScrollBar().valueChanged.connect(self.table_src.verticalScrollBar().setValue)
        
        self.splitter.addWidget(self.table_src)
        self.splitter.addWidget(self.table_trg)
        self.splitter.addWidget(self.splitter_spacer)
        self.splitter_spacer.hide()
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 0)
        
        right_panel.addWidget(self.splitter, 0) 
        right_panel.addStretch(1) # Tlačí tabulky nahoru, aby se neroztahovaly na výšku
        
        layout.addLayout(left_panel, 1); layout.addLayout(right_panel, 4)

        # Signaling
        self.btn_load_xdf.clicked.connect(self.load_xdf_action)
        self.btn_load_src.clicked.connect(lambda: self.load_bin_action('src'))
        self.btn_load_trg.clicked.connect(lambda: self.load_bin_action('trg'))
        self.btn_export.clicked.connect(self.export_xdf_action)
        self.btn_fuzzy.clicked.connect(self.start_fuzzy_scan)
        # Table configurations (itemSelectionChanged)
        pass

    def load_xdf_action(self):
        path, _ = QFileDialog.getOpenFileName(self, "XDF", "", "XDF (*.xdf)")
        if path:
            self.xdf_tree, self.all_maps = self.engine.parse_xdf(path)
            self.btn_fuzzy.setEnabled(False)
            self.update_list()

    def load_bin_action(self, mode):
        path, _ = QFileDialog.getOpenFileName(self, "BIN", "", "BIN (*.bin)")
        if not path: return
        import os
        filename = os.path.basename(path)
        data = open(path, "rb").read()
        if mode == 'src': 
            self.bin_src = data
            self.src_filename = str(filename)
        else: 
            self.bin_trg = data
            self.trg_filename = str(filename)
        
        if self.bin_src and self.bin_trg and self.all_maps:
            self.start_scan()

    def start_scan(self):
        self.lbl_info.setText("Starting scan...")
        self.progress.setValue(0)
        self.set_buttons_enabled(False)
        
        self.worker = ScanWorker(self.engine, self.all_maps, self.bin_src, self.bin_trg)
        self.worker.progress_update.connect(self.progress.setValue)
        self.worker.log_message.connect(self.lbl_info.setText)
        self.worker.scanning_finished.connect(self.on_scan_finished)
        self.worker.start()

    def on_scan_finished(self, found, unique):
        self.set_buttons_enabled(True)
        self.update_list()
        self.lbl_info.setText(f"Finished. Found: {found} (Unique: {unique})")
        
        # Pokud jsou nenalezené mapy, povolíme Fuzzy Search
        total = len(self.all_maps)
        if found < total:
            self.btn_fuzzy.setEnabled(True)
            self.lbl_info.setText(f"Finished. Found: {found}/{total}. You can try Fuzzy Search.")

    def start_fuzzy_scan(self):
        self.lbl_info.setText("Starting Fuzzy Search...")
        self.progress.setValue(0)
        self.set_buttons_enabled(False)
        self.btn_fuzzy.setEnabled(False)
        
        self.fuzzy_worker = FuzzyScanWorker(self.engine, self.all_maps, self.bin_src, self.bin_trg)
        self.fuzzy_worker.progress_update.connect(self.progress.setValue)
        self.fuzzy_worker.log_message.connect(self.lbl_info.setText)
        self.fuzzy_worker.fuzzy_finished.connect(self.on_fuzzy_finished)
        self.fuzzy_worker.start()

    def on_fuzzy_finished(self, fuzzy_count):
        self.set_buttons_enabled(True)
        self.update_list()
        self.lbl_info.setText(f"Fuzzy Search finished. Newly found: {fuzzy_count}")
        self.btn_fuzzy.setEnabled(False) # Already tried

    def set_buttons_enabled(self, enabled):
        self.btn_load_xdf.setEnabled(enabled)
        self.btn_load_src.setEnabled(enabled)
        self.btn_load_trg.setEnabled(enabled)
        self.btn_export.setEnabled(enabled)

    def update_list(self):
        q = self.search.text().lower()
        self.table_map.setRowCount(0)
        self.table_scat.setRowCount(0)
        
        def get_sort_key(m):
            if m.match_type == "UNIQUE": return 0
            if m.match_type == "SEQUENTIAL": return 1
            if m.match_type == "FUZZY": return 2
            if m.match_type == "AMBIGUOUS": return 3
            return 3 # NONE/ERROR

        sorted_maps = sorted(self.all_maps.values(), key=get_sort_key)
        
        for m in sorted_maps:
            if q in m.name.lower():
                if m.match_type in ["NONE", "ERROR"] and m.match_count == 0:
                     continue
                
                target = self.table_scat if m.is_scalar else self.table_map
                
                # Unified status marker
                if m.match_type == "UNIQUE":
                    marker = "●"
                    color = Qt.GlobalColor.darkGreen
                elif m.match_type == "SEQUENTIAL":
                    marker = "● SEQ"
                    color = QColor("#FF8C00")
                elif m.match_type == "FUZZY":
                    marker = "● FUZZY"
                    color = QColor("#DAA520")
                elif m.match_type == "AMBIGUOUS":
                    marker = f"● [{m.match_count}x]"
                    color = Qt.GlobalColor.red
                else:
                    marker = "● NONE"
                    color = Qt.GlobalColor.gray
                
                row = target.rowCount()
                target.insertRow(row)
                
                # Adresa (0. sloupec)
                addr_text = f"0x{m.target_addr:X}" if m.target_addr > 0 else "???"
                it_addr = QTableWidgetItem(addr_text)
                it_addr.setForeground(QBrush(color))
                it_addr.setData(Qt.ItemDataRole.UserRole, m.name) # Store name for select_map
                target.setItem(row, 0, it_addr)
                
                # Name + Marker + Extra info (1st column)
                name_text = f"{marker} {m.name}"
                extra = []
                if m.is_deep: extra.append("deep")
                if m.x_is_deep: extra.append("x-deep")
                if m.y_is_deep: extra.append("y-deep")
                if extra:
                    name_text += " (" + ", ".join(extra) + ")"
                
                it_name = QTableWidgetItem(name_text)
                it_name.setForeground(QBrush(color))
                target.setItem(row, 1, it_name)

    def export_xdf_action(self):
        if not self.xdf_tree:
            self.lbl_info.setText("Error: XDF not loaded.")
            return
            
        # Dynamic filename
        default_name = "output.xdf"
        if self.src_filename and self.trg_filename:
            s_base = self.src_filename.split('.')[0]
            t_base = self.trg_filename.split('.')[0]
            default_name = f"{s_base}_to_{t_base}.xdf"
            
        path, _ = QFileDialog.getSaveFileName(self, "Save XDF", default_name, "XDF (*.xdf)")
        if path:
            self.engine.write_xdf(self.xdf_tree, self.all_maps, path, include_deep=self.cb_deep_export.isChecked())
            self.lbl_info.setText(f"Saved to {path}")

    def select_map(self):
        target = self.table_map if self.tabs.currentIndex() == 0 else self.table_scat
        items = target.selectedItems()
        if not items: return
        
        name = items[0].data(Qt.ItemDataRole.UserRole)
        m = self.all_maps.get(name)
        if m and self.bin_src:
            # 1. Basic info
            deep_info = ""
            if m.is_deep:
                deep_info = f"<br/><font color='#fff'><b>Deep Match (Z):</b> +{m.deep_l}b vlevo, +{m.deep_r}b vpravo</font>"
            if m.x_is_deep:
                deep_info += f"<br/><font color='#fff'><b>Deep Match (X):</b> +{m.x_deep_l}b vlevo, +{m.x_deep_r}b vpravo</font>"
            if m.y_is_deep:
                deep_info += f"<br/><font color='#fff'><b>Deep Match (Y):</b> +{m.y_deep_l}b vlevo, +{m.y_deep_r}b vpravo</font>"

            map_markers = ""
            if m.is_deep: map_markers += " (deep)"
            if m.x_is_deep: map_markers += " (x-deep)"
            if m.y_is_deep: map_markers += " (y-deep)"
            
            addr_str = f"0x{m.target_addr:X}" if m.target_addr > 0 else "???"
            if m.match_type == "AMBIGUOUS":
                addr_str = f"DUPLICATES ({m.match_count}x)"
                
            self.lbl_info.setText(f"Map: {m.name}{map_markers} ({addr_str}){deep_info}")

            # 2. Helper function for reading axes
            def get_axis_vals(bin_data, addr, count, is16, is_signed, eq):
                if addr > 0:
                    return [m.calculate(self.engine.read_raw(bin_data, addr + i*(2 if is16 else 1), is16, is_signed), eq, is16, is_signed) for i in range(count)]
                return None

            # 3. Orientation and dimensions (MLHFM and 1D maps)
            is_1d_swap = (m.z_cols == 1 and m.z_rows > 1 and m.x_count > 1 and m.y_count <= 1)
            
            # 4. Statuses and colors for axes
            x_status = ""; x_color = Qt.GlobalColor.black
            y_status = ""; y_color = Qt.GlobalColor.black
            
            # 5. Filling tables
            if m.match_type == "AMBIGUOUS":
                # SPECIAL MODE FOR DUPLICATES
                src_x = get_axis_vals(self.bin_src, m.x_addr, m.z_cols, m.x_is16, m.x_signed, m.x_eq)
                src_y = get_axis_vals(self.bin_src, m.y_addr, m.z_rows, m.y_is16, m.y_signed, m.y_eq)
                real_rows, real_cols = m.z_rows, m.z_cols
                
                self.ui_man.setup_table(self.table_src, real_rows, real_cols, src_x, src_y)
                self.ui_man.fill_table(self.table_src, m, self.bin_src, m.z_addr, self.engine)
                
                # Show address list on the right
                self.ui_man.setup_table(self.table_trg, len(m.matches), 1, ["Possible addresses (Ambig.)"], None)
                for i, addr in enumerate(m.matches):
                    self.table_trg.setItem(i, 0, QTableWidgetItem(f"0x{addr:X}"))
                
                self.splitter.setOrientation(Qt.Orientation.Horizontal)
                self.splitter_spacer.show()
                max_h = 800
                self.splitter.setStretchFactor(0, 1); self.splitter.setStretchFactor(1, 1); self.splitter.setStretchFactor(2, 0)
            else:
                # STANDARD MODE
                if is_1d_swap:
                    src_x = None
                    src_y = get_axis_vals(self.bin_src, m.x_addr, m.z_rows, m.x_is16, m.x_signed, m.x_eq)
                    trg_x = None
                    trg_y = get_axis_vals(self.bin_trg, m.target_x_addr, m.z_rows, m.x_is16, m.x_signed, m.x_eq)
                    
                # Large MLHFM (512) -> always indices
                    if m.z_rows > 100:
                        src_y = [str(i+1) for i in range(m.z_rows)]
                        trg_y = [str(i+1) for i in range(m.z_rows)]
                    
                    real_rows, real_cols = m.z_rows, 1
                    curr_x_match = m.x_match_type
                    curr_y_match = "NONE"
                else:
                    src_x = get_axis_vals(self.bin_src, m.x_addr, m.z_cols, m.x_is16, m.x_signed, m.x_eq)
                    src_y = get_axis_vals(self.bin_src, m.y_addr, m.z_rows, m.y_is16, m.y_signed, m.y_eq)
                    trg_x = get_axis_vals(self.bin_trg, m.target_x_addr, m.z_cols, m.x_is16, m.x_signed, m.x_eq)
                    trg_y = get_axis_vals(self.bin_trg, m.target_y_addr, m.z_rows, m.y_is16, m.y_signed, m.y_eq)
                    real_rows, real_cols = m.z_rows, m.z_cols
                    curr_x_match = m.x_match_type
                    curr_y_match = m.y_match_type

                if not is_1d_swap and m.x_addr > 0:
                    if curr_x_match == "UNIQUE": x_color = Qt.GlobalColor.darkGreen
                    elif curr_x_match == "OFFSET": x_status = " (x-off)"; x_color = Qt.GlobalColor.darkGreen
                    elif curr_x_match == "GUESS": x_status = " (?x)"; x_color = QColor("#FF8C00")
                    else: x_status = " [NOT FOUND]"; x_color = Qt.GlobalColor.red

                vis_y_match = curr_x_match if is_1d_swap else curr_y_match
                if vis_y_match == "UNIQUE": y_color = Qt.GlobalColor.darkGreen
                elif vis_y_match == "OFFSET": y_status = " (off)"; y_color = Qt.GlobalColor.darkGreen
                elif vis_y_match == "GUESS": y_status = " (?)"; y_color = QColor("#FF8C00")
                elif m.y_addr > 0 or (is_1d_swap and m.x_addr > 0):
                    y_status = " [?]"; y_color = Qt.GlobalColor.red

            # 5. Splitter configuration (orientation)
                if real_rows > 32 and real_cols == 1:
                    self.splitter.setOrientation(Qt.Orientation.Horizontal)
                    self.splitter_spacer.show()
                    max_h = 800
                    self.splitter.setStretchFactor(0, 0); self.splitter.setStretchFactor(1, 0); self.splitter.setStretchFactor(2, 1)
                else:
                    self.splitter.setOrientation(Qt.Orientation.Vertical)
                    self.splitter_spacer.hide()
                    max_h = 450
                    self.splitter.setStretchFactor(0, 1); self.splitter.setStretchFactor(1, 1); self.splitter.setStretchFactor(2, 0)

            # 6. Filling tables
                self.ui_man.setup_table(self.table_src, real_rows, real_cols, src_x, src_y)
                self.ui_man.fill_table(self.table_src, m, self.bin_src, m.z_addr, self.engine)
                
                self.ui_man.setup_table(self.table_trg, real_rows, real_cols, 
                                        [str(h) + x_status for h in trg_x] if trg_x else None, 
                                        [str(h) + y_status for h in trg_y] if trg_y else None)
                self.ui_man.fill_table(self.table_trg, m, self.bin_trg, m.target_addr, self.engine, is_source=False)

            # 7. Coloring headers in target table
                if trg_x:
                    for col in range(real_cols):
                        item = self.table_trg.horizontalHeaderItem(col)
                        if item: item.setForeground(QBrush(x_color))
                if trg_y:
                    for row in range(real_rows):
                        item = self.table_trg.verticalHeaderItem(row)
                        if item: item.setForeground(QBrush(y_color))

            self.ui_man.auto_set_height(self.table_src, max_h)
            self.ui_man.auto_set_height(self.table_trg, max_h)

if __name__ == "__main__":
    app = QApplication(sys.argv); ex = ME7TransferApp(); ex.show(); sys.exit(app.exec())
