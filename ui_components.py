from PyQt6.QtWidgets import QTableWidgetItem, QHeaderView
from PyQt6.QtGui import QColor

class UIManager:
    @staticmethod
    def setup_table(table, rows, cols, headers_x=None, headers_y=None):
        table.setRowCount(rows)
        table.setColumnCount(cols)
        if headers_x: 
            table.setHorizontalHeaderLabels([str(x) for x in headers_x])
        else:
            table.setHorizontalHeaderLabels([str(i+1) for i in range(cols)])
            
        if headers_y: 
            table.setVerticalHeaderLabels([str(y) for y in headers_y])
        else:
            table.setVerticalHeaderLabels([str(i+1) for i in range(rows)])
        
        if cols > 1:
            table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        else:
            table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        
        table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)

    @staticmethod
    def fill_table(table, m, bin_data, start_addr, engine, is_source=True):
        if start_addr == -1: return
        step = 2 if m.z_is16 else 1
        prec = 4 if m.is_scalar else 2
        
        for r in range(m.z_rows):
            for c in range(m.z_cols):
                idx = (r * m.z_cols) + c
                raw = engine.read_raw(bin_data, start_addr + idx*step, m.z_is16, m.z_signed)
                val_str = m.calculate(raw, m.z_eq, m.z_is16, m.z_signed, prec)
                table.setItem(r, c, QTableWidgetItem(val_str))

    @staticmethod
    def auto_set_height(table, max_h=500):
        # Calculate required height: header + all rows + margin
        h = table.horizontalHeader().height()
        for r in range(table.rowCount()):
            h += table.rowHeight(r)
        
        # Add a small margin for grid/border
        final_h = min(h + 4, max_h)
        table.setMinimumHeight(final_h)
        table.setMaximumHeight(final_h)
        table.setFixedHeight(final_h)
