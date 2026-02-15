import sys
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QListWidget, QTableWidget, QPushButton, 
                             QFileDialog, QLabel, QLineEdit, QSplitter, QTabWidget, 
                             QProgressBar, QListWidgetItem)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QColor, QBrush, QIcon
from data_engine import DataEngine
from ui_components import UIManager

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
            
            # Scan Z
            matches = self.engine.scan_for_matches(self.bin_src, self.bin_trg, m.z_addr, m.z_rows, m.z_cols, m.z_is16)
            m.matches = matches
            m.match_count = len(matches)
            
            if i % 10 == 0:
                self.progress_update.emit(int((i / total) * 90)) # 0-90% for scanning

        # 2. Resolve Matches (Sequential logic + Axis scanning)
        self.log_message.emit("Analyzuji duplicity a osy...")
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

class ME7TransferApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("XDF Transfer Tool v0.9.4 (Pre-release)")
        self.setWindowIcon(QIcon("favicon.ico"))
        self.resize(1500, 900)
        
        # Inicializace modulů
        self.engine = DataEngine()
        self.ui_man = UIManager()
        self.bin_src = self.bin_trg = self.xdf_tree = None
        self.src_filename = self.trg_filename = ""
        self.all_maps = {}
        self.worker = None

        # Sestavení UI
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QHBoxLayout(main_widget)

        # Panel nástrojů
        left_panel = QVBoxLayout()
        self.btn_load_xdf = QPushButton("1. Načíst XDF")
        self.btn_load_src = QPushButton("2. Načíst ZDROJ BIN")
        self.btn_load_trg = QPushButton("3. Načíst CÍL BIN")
        
        self.progress = QProgressBar()
        self.progress.setValue(0)
        self.progress.setTextVisible(True)
        
        self.btn_export = QPushButton("4. EXPORT XDF")
        self.btn_export.setStyleSheet("background: #aa0000; color: white; font-weight: bold;")
        
        self.search = QLineEdit()
        self.search.setPlaceholderText("Hledat...")
        self.search.textChanged.connect(self.update_list)
        
        self.tabs = QTabWidget()
        self.list_map = QListWidget(); self.list_scat = QListWidget()
        self.tabs.addTab(self.list_map, "Mapy"); self.tabs.addTab(self.list_scat, "Skaláry")
        
        self.lbl_info = QLabel("Stav: Připraven")
        self.lbl_info.setWordWrap(True)
        self.lbl_info.setMaximumWidth(280) # Zabrání roztahování panelu
        self.lbl_info.setStyleSheet("color: #555; font-size: 11px; padding: 2px;")
        
        # Legenda značek
        self.lbl_legend = QLabel(
            "<b>Legenda značek:</b><br/>"
            "<font color='#008000'>(x-off)</font>: Osa sedí na offset (Jisté)<br/>"
            "<font color='#FF8C00'>(?x)</font>: Odhad osy (Více shod)<br/>"
            "<font color='#B8860B'>(seq)</font>: Sekvenční mapa (Duplicita)<br/>"
            "<font color='red'>[NENAŠLO SE]</font>: Osa nenalezena"
        )
        self.lbl_legend.setStyleSheet("color: #444; background: rgba(0,0,0,5%); border-top: 1px solid #ccc; padding-top: 10px; font-size: 10px;")
        
        # Layout components
        left_panel.addWidget(self.btn_load_xdf)
        left_panel.addWidget(self.btn_load_src)
        left_panel.addWidget(self.btn_load_trg)
        left_panel.addWidget(QLabel("Průběh:"))
        left_panel.addWidget(self.progress)
        left_panel.addWidget(self.btn_export)
        left_panel.addWidget(self.search)
        left_panel.addWidget(self.tabs)
        left_panel.addWidget(self.lbl_info)
        left_panel.addSpacing(10)
        left_panel.addWidget(self.lbl_legend)

        # Tabulky - zabalení do layoutu se stretchem dole, aby malé mapy nebyly roztažené
        right_panel = QVBoxLayout()
        self.splitter = QSplitter(Qt.Orientation.Vertical)
        self.splitter.setHandleWidth(2) # Užší mezera mezi tabulkami
        self.table_src = QTableWidget(); self.table_trg = QTableWidget()
        self.splitter_spacer = QWidget() # Pružina pro horizontální režim
        
        # Synchronizace scrollování
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

        # Signalizace
        self.btn_load_xdf.clicked.connect(self.load_xdf_action)
        self.btn_load_src.clicked.connect(lambda: self.load_bin_action('src'))
        self.btn_load_trg.clicked.connect(lambda: self.load_bin_action('trg'))
        self.btn_export.clicked.connect(self.export_xdf_action)
        self.list_map.itemClicked.connect(self.select_map)
        self.list_scat.itemClicked.connect(self.select_map)

    def load_xdf_action(self):
        path, _ = QFileDialog.getOpenFileName(self, "XDF", "", "XDF (*.xdf)")
        if path:
            self.xdf_tree, self.all_maps = self.engine.parse_xdf(path)
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
        self.lbl_info.setText("Startuji skenování...")
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
        self.lbl_info.setText(f"Hotovo. Nalezeno: {found} (Unikátní: {unique})")

    def set_buttons_enabled(self, enabled):
        self.btn_load_xdf.setEnabled(enabled)
        self.btn_load_src.setEnabled(enabled)
        self.btn_load_trg.setEnabled(enabled)
        self.btn_export.setEnabled(enabled)

    def update_list(self):
        q = self.search.text().lower()
        self.list_map.clear(); self.list_scat.clear()
        
        # Sorting groups: UNIQUE (0), SEQUENTIAL (1), AMBIGUOUS (2)
        # We need to sort logic
        
        def get_sort_key(m):
            if m.match_type == "UNIQUE": return 0
            if m.match_type == "SEQUENTIAL": return 1
            if m.match_type == "AMBIGUOUS": return 2
            return 3 # NONE/ERROR

        sorted_maps = sorted(self.all_maps.values(), key=get_sort_key)
        
        for m in sorted_maps:
            if q in m.name.lower():
                if m.match_type in ["NONE", "ERROR"] and m.match_count == 0:
                     continue
                
                target = self.list_scat if m.is_scalar else self.list_map
                
                if m.match_type == "UNIQUE":
                    status = "" # Čistý název pro unikátní
                    color = Qt.GlobalColor.darkGreen
                elif m.match_type == "SEQUENTIAL":
                    status = "(seq)"
                    color = QColor("#FF8C00") # Dark Orange
                elif m.match_type == "AMBIGUOUS":
                    status = f"[{m.match_count}x]"
                    color = Qt.GlobalColor.red
                else:
                    status = "[???]"
                    color = Qt.GlobalColor.gray
                
                text = f"{status} {m.name}".strip()
                item = QListWidgetItem(text)
                item.setData(Qt.ItemDataRole.UserRole, m.name) # Uložíme čisté jméno jako data
                item.setForeground(QBrush(color))
                target.addItem(item)

    def export_xdf_action(self):
        if not self.xdf_tree:
            self.lbl_info.setText("Chyba: Není načten XDF.")
            return
            
        # Dynamický název souboru
        default_name = "output.xdf"
        if self.src_filename and self.trg_filename:
            s_base = self.src_filename.split('.')[0]
            t_base = self.trg_filename.split('.')[0]
            default_name = f"{s_base}_to_{t_base}.xdf"
            
        path, _ = QFileDialog.getSaveFileName(self, "Uložit XDF", default_name, "XDF (*.xdf)")
        if path:
            self.engine.write_xdf(self.xdf_tree, self.all_maps, path)
            self.lbl_info.setText(f"Uloženo do {path}")

    def select_map(self, item):
        name = item.data(Qt.ItemDataRole.UserRole)
        m = self.all_maps.get(name)
        if m and self.bin_src:
            # Helper to read axis values
            def get_axis_vals(bin_data, addr, count, is16, is_signed, eq):
                if addr > 0:
                    return [m.calculate(self.engine.read_raw(bin_data, addr + i*(2 if is16 else 1), is16, is_signed), eq, is16, is_signed) for i in range(count)]
                return None

            # SMART SWAP OS pro 1D Mapy:
            # XDF často definuje lineární mapy (např. MLHFM) jako 512x1.
            # V XDF je osa X ta dlouhá (512), ale v našem GUI (tabulce) je to osa Y (řádky).
            # Musíme tedy prohodit data os, aby to v GUI vypadalo správně.
            
            is_1d_swap = (m.z_cols == 1 and m.z_rows > 1 and m.x_count > 1 and m.y_count <= 1)

            if is_1d_swap:
                # Zdroj
                src_x = None # Sloupec je jen jeden, nepotřebuje titulek
                src_y = get_axis_vals(self.bin_src, m.x_addr, m.z_rows, m.x_is16, m.x_signed, m.x_eq)
                # Cíl
                trg_x_addr = -1
                trg_y_addr = m.target_x_addr if m.target_x_addr > 0 else -1
                trg_x = None
                trg_y = get_axis_vals(self.bin_trg, trg_y_addr, m.z_rows, m.x_is16, m.x_signed, m.x_eq)
                
                # Pro barvení musíme vědět, že Y status v GUI teď odpovídá X statusu z modelu
                curr_x_match_type = m.x_match_type 
                curr_y_match_type = "NONE"
            else:
                # Standardní 2D nebo krátká 1D
                src_x = get_axis_vals(self.bin_src, m.x_addr, m.z_cols, m.x_is16, m.x_signed, m.x_eq)
                src_y = get_axis_vals(self.bin_src, m.y_addr, m.z_rows, m.y_is16, m.y_signed, m.y_eq)
                trg_x_addr = m.target_x_addr if m.target_x_addr > 0 else -1
                trg_y_addr = m.target_y_addr if m.target_y_addr > 0 else -1
                trg_x = get_axis_vals(self.bin_trg, trg_x_addr, m.z_cols, m.x_is16, m.x_signed, m.x_eq)
                trg_y = get_axis_vals(self.bin_trg, trg_y_addr, m.z_rows, m.y_is16, m.y_signed, m.y_eq)
                
                curr_x_match_type = m.x_match_type
                curr_y_match_type = m.y_match_type

            # Inteligentní orientace tabulek:
            if m.z_rows > 32 and m.z_cols == 1:
                self.splitter.setOrientation(Qt.Orientation.Horizontal)
                self.splitter_spacer.show()
                max_h = 800
                # Nastavíme stretch faktory: Tab1=0, Tab2=0, Spacer=1 -> Tabulky se smrsknou doleva
                self.splitter.setStretchFactor(0, 0)
                self.splitter.setStretchFactor(1, 0)
                self.splitter.setStretchFactor(2, 1)
            else:
                self.splitter.setOrientation(Qt.Orientation.Vertical)
                self.splitter_spacer.hide()
                max_h = 450
                # Ve vertikálním režimu nechat standardní stretch
                self.splitter.setStretchFactor(0, 1)
                self.splitter.setStretchFactor(1, 1)
                self.splitter.setStretchFactor(2, 0)

            self.ui_man.setup_table(self.table_src, m.z_rows, m.z_cols, src_x, src_y)
            self.ui_man.fill_table(self.table_src, m, self.bin_src, m.z_addr, self.engine)
            self.ui_man.auto_set_height(self.table_src, max_h)
            
            # Info o osách pro GUI (synchronizace značek s XDF)
            x_status = ""; x_color = Qt.GlobalColor.black
            # X Status v GUI odpovídá modelu:
            final_x_match = "NONE" if is_1d_swap else curr_x_match_type
            if not is_1d_swap and m.x_addr > 0:
                if final_x_match == "UNIQUE": x_color = Qt.GlobalColor.darkGreen
                elif final_x_match == "OFFSET": x_status = " (x-off)"; x_color = Qt.GlobalColor.darkGreen
                elif final_x_match == "GUESS": x_status = " (?x)"; x_color = QColor("#FF8C00")
                else: x_status = " [NENAŠLO SE]"; x_color = Qt.GlobalColor.red

            y_status = ""; y_color = Qt.GlobalColor.black
            # Y Status v GUI odpovídá modelu (pokud byl swap, Y v GUI je X z modelu):
            final_y_match = curr_x_match_type if is_1d_swap else curr_y_match_type
            
            if final_y_match == "UNIQUE":
                y_status = ""; y_color = Qt.GlobalColor.darkGreen
            elif final_y_match == "OFFSET":
                y_status = " (y-off)" if not is_1d_swap else " (x-off)"
                y_color = Qt.GlobalColor.darkGreen
            elif final_y_match == "GUESS":
                y_status = " (?y)" if not is_1d_swap else " (?x)"
                y_color = QColor("#FF8C00")
            elif final_y_match == "NONE" and (m.y_addr > 0 or (is_1d_swap and m.x_addr > 0)):
                y_status = " [NENAŠLO SE]"; y_color = Qt.GlobalColor.red


            self.ui_man.setup_table(self.table_trg, m.z_rows, m.z_cols, 
                                    [str(h) + x_status for h in trg_x] if trg_x else None, 
                                    [str(h) + y_status for h in trg_y] if trg_y else None)
            self.ui_man.fill_table(self.table_trg, m, self.bin_trg, m.target_addr, self.engine)
            
            # Barevné odlišení pozadí hlaviček (volitelné UX)
            # trg_table setHorizontalHeaderItem color could be used here if needed.
            if trg_x:
                for col in range(m.z_cols):
                    item = self.table_trg.horizontalHeaderItem(col)
                    if item: item.setForeground(QBrush(x_color))
            if trg_y:
                for row in range(m.z_rows):
                    item = self.table_trg.verticalHeaderItem(row)
                    if item: item.setForeground(QBrush(y_color))
            
            # Dynamická výška podle obsahu
            self.ui_man.auto_set_height(self.table_trg, max_h)

if __name__ == "__main__":
    app = QApplication(sys.argv); ex = ME7TransferApp(); ex.show(); sys.exit(app.exec())
