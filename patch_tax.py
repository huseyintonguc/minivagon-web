with open("app.py", "r") as f:
    content = f.read()

# 1. Cast userId to int in payload
content = content.replace('"userId": user_id,', '"userId": safe_int(user_id),')
content = content.replace('"companyId": company_id_val,', '"companyId": safe_int(company_id_val),')

# 2. Fix totalTax schema
old_invoice_info = """
      "invoiceInfo": {
        "invoiceType": "EARSIVFATURA",
        "invoiceTypeCode": "SATIS",
        "totalTax": vergi_kurus
      },
      "invoiceLines": [],
      "taxes": {
        "taxAmount": vergi_kurus,
        "taxableAmount": vergisiz_kurus
      },
"""
new_invoice_info = """
      "invoiceInfo": {
        "invoiceType": "EARSIVFATURA",
        "invoiceTypeCode": "SATIS"
      },
      "invoiceLines": [],
      "totalTax": {
        "taxAmount": vergi_kurus,
        "taxableAmount": vergisiz_kurus
      },
"""
content = content.replace(old_invoice_info, new_invoice_info)

with open("app.py", "w") as f:
    f.write(content)
