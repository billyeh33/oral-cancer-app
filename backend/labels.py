"""Class names and risk levels shared by the CNN code and the API."""

CLASS_NAMES = ("Normal", "Benign", "OPMD", "Oral Cancer")
RISK_LEVELS = {
    "Normal": "低風險",
    "Benign": "中低風險",
    "OPMD": "中高風險",
    "Oral Cancer": "高風險",
}
