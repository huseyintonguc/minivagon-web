import re

with open("app.py", "r") as f:
    content = f.read()

# Fix re import and backslash escaping
content = content.replace("import base64\nimport json", "import base64\nimport json\nimport re")
content = content.replace("tel = re.sub(r'[^0-9\+]', '', tel)", "tel = re.sub(r'[^0-9+]', '', tel)")
content = content.replace('tel = re.sub(r"[^0-9+]", "", tel)', "tel = re.sub(r'[^0-9+]', '', tel)")

# Check if changes applied
if "import re" in content:
    print("re imported")
else:
    print("re NOT imported")

with open("app.py", "w") as f:
    f.write(content)
