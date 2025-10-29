import sqlite3

# Kết nối hoặc tạo file fruits.db
conn = sqlite3.connect("fruits.db")
cursor = conn.cursor()

# Tạo bảng lưu thông tin trái cây
cursor.execute("""
CREATE TABLE IF NOT EXISTS fruits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE,
    price TEXT,
    description TEXT
)
""")

# Dữ liệu 10 loại trái cây mẫu
fruits_data = [
    ("chuối", "25.000đ/kg", "Chuối chín vàng, vị ngọt tự nhiên, giàu kali và vitamin B6, tốt cho tim mạch."),
    ("táo", "45.000đ/kg", "Táo đỏ tươi, giòn ngọt, chứa nhiều chất chống oxy hóa, giúp đẹp da và hỗ trợ tiêu hóa."),
    ("cam", "35.000đ/kg", "Cam mọng nước, giàu vitamin C, giúp tăng cường miễn dịch và làm đẹp da."),
    ("xoài", "40.000đ/kg", "Xoài chín vàng, thơm ngọt, chứa nhiều vitamin A và C, tốt cho thị lực."),
    ("nho", "60.000đ/kg", "Nho tươi ngon, nhiều dưỡng chất, giúp giảm căng thẳng và tốt cho tim mạch."),
    ("dưa hấu", "20.000đ/kg", "Dưa hấu ngọt mát, chứa nhiều nước, giúp giải nhiệt và hỗ trợ tiêu hóa."),
    ("dứa", "30.000đ/kg", "Dứa (thơm) có vị chua ngọt, chứa enzyme hỗ trợ tiêu hóa và làm đẹp da."),
    ("dâu tây", "120.000đ/kg", "Dâu tây đỏ mọng, giàu vitamin C và chất chống oxy hóa, giúp làm đẹp và tốt cho da."),
    ("lê", "50.000đ/kg", "Lê ngọt mát, nhiều nước, giúp thanh lọc cơ thể và tốt cho phổi."),
    ("thanh long", "25.000đ/kg", "Thanh long tươi mát, ít calo, nhiều chất xơ, giúp hỗ trợ tiêu hóa và giảm cân."),
]

# Thêm dữ liệu vào bảng
cursor.executemany("""
INSERT OR IGNORE INTO fruits (name, price, description)
VALUES (?, ?, ?)
""", fruits_data)

conn.commit()
conn.close()

print("✅ Đã tạo database fruits.db thành công với 10 loại trái cây!")
