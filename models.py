class XDFMap:
    def __init__(self, name, node, is_scalar=False):
        self.name = name
        self.node = node
        self.is_scalar = is_scalar
        self.z_addr, self.z_is16, self.z_signed, self.z_eq = 0, False, False, "X"
        self.z_rows, self.z_cols = 1, 1
        self.x_addr, self.x_is16, self.x_signed, self.x_eq, self.x_count = 0, False, False, "X", 0
        self.y_addr, self.y_is16, self.y_signed, self.y_eq, self.y_count = 0, False, False, "X", 0
        self.match_percent = 0
        self.target_addr = -1
        self.target_x_addr = -1
        self.target_y_addr = -1
        self.match_count = 0  # Number of matches found
        self.matches = []     # List of addresses for all matches
        
        # New for Phase 2
        self.x_matches = []
        self.y_matches = []
        # match_type: "NONE", "UNIQUE", "SEQUENTIAL", "AMBIGUOUS", "FUZZY"
        self.match_type = "NONE"
        # x/y_match_type: "NONE", "UNIQUE", "OFFSET", "GUESS"
        self.x_match_type = "NONE"
        self.y_match_type = "NONE"
        self.is_deep = False
        self.deep_l, self.deep_r = 0, 0
        
        # New for Axis context
        self.x_is_deep = False
        self.x_deep_l, self.x_deep_r = 0, 0
        self.y_is_deep = False
        self.y_deep_l, self.y_deep_r = 0, 0

    def calculate(self, raw_val, eq, is16, signed, precision=2):
        val = raw_val
        if signed:
            # Classic ME7 signed byte interpretation:
            # Values 128-255 are interpreted as -128 to -1
            if not is16: # 8-bit
                if val > 127:
                    val -= 256
            else: # 16-bit
                if val > 32767:
                    val -= 65536
        
        try:
            # Replace X in equation with the calculated value
            res = eval(eq.replace('X', str(val)).replace(',', '.'), {"__builtins__": None}, {})
            return f"{res:.{precision}f}" if isinstance(res, float) else str(res)
        except:
            return str(val)
