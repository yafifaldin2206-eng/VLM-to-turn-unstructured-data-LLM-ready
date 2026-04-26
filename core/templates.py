"""
Built-in extraction templates with pre-defined schemas.
"""

from app.models.schemas import TemplateInfo, TemplateType

TEMPLATES: dict[TemplateType, TemplateInfo] = {
    TemplateType.INVOICE: TemplateInfo(
        id=TemplateType.INVOICE,
        name="Invoice",
        description="Extract invoice data including line items, totals, parties.",
        example_fields=[
            "invoice_number", "invoice_date", "due_date",
            "vendor_name", "vendor_address", "vendor_tax_id",
            "customer_name", "customer_address",
            "line_items", "subtotal", "tax", "total", "currency",
            "payment_terms", "bank_details",
        ],
        output_schema={
            "type": "object",
            "properties": {
                "invoice_number": {"type": ["string", "null"]},
                "invoice_date": {"type": ["string", "null"], "description": "ISO 8601 date"},
                "due_date": {"type": ["string", "null"]},
                "vendor": {
                    "type": "object",
                    "properties": {
                        "name": {"type": ["string", "null"]},
                        "address": {"type": ["string", "null"]},
                        "tax_id": {"type": ["string", "null"]},
                        "email": {"type": ["string", "null"]},
                        "phone": {"type": ["string", "null"]},
                    },
                },
                "customer": {
                    "type": "object",
                    "properties": {
                        "name": {"type": ["string", "null"]},
                        "address": {"type": ["string", "null"]},
                        "tax_id": {"type": ["string", "null"]},
                    },
                },
                "line_items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "description": {"type": "string"},
                            "quantity": {"type": ["number", "null"]},
                            "unit_price": {"type": ["number", "null"]},
                            "amount": {"type": ["number", "null"]},
                        },
                    },
                },
                "subtotal": {"type": ["number", "null"]},
                "tax_amount": {"type": ["number", "null"]},
                "tax_rate": {"type": ["number", "null"]},
                "total": {"type": ["number", "null"]},
                "currency": {"type": ["string", "null"]},
                "payment_terms": {"type": ["string", "null"]},
                "notes": {"type": ["string", "null"]},
            },
        },
    ),
    TemplateType.RECEIPT: TemplateInfo(
        id=TemplateType.RECEIPT,
        name="Receipt",
        description="Extract POS receipt data.",
        example_fields=["merchant", "date", "items", "total", "payment_method"],
        output_schema={
            "type": "object",
            "properties": {
                "merchant_name": {"type": ["string", "null"]},
                "merchant_address": {"type": ["string", "null"]},
                "date": {"type": ["string", "null"]},
                "time": {"type": ["string", "null"]},
                "receipt_number": {"type": ["string", "null"]},
                "items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "quantity": {"type": ["number", "null"]},
                            "price": {"type": ["number", "null"]},
                        },
                    },
                },
                "subtotal": {"type": ["number", "null"]},
                "tax": {"type": ["number", "null"]},
                "tip": {"type": ["number", "null"]},
                "total": {"type": ["number", "null"]},
                "payment_method": {"type": ["string", "null"]},
                "currency": {"type": ["string", "null"]},
            },
        },
    ),
    TemplateType.BUSINESS_CARD: TemplateInfo(
        id=TemplateType.BUSINESS_CARD,
        name="Business Card",
        description="Extract contact information from business cards.",
        example_fields=["name", "title", "company", "email", "phone", "address", "website"],
        output_schema={
            "type": "object",
            "properties": {
                "full_name": {"type": ["string", "null"]},
                "first_name": {"type": ["string", "null"]},
                "last_name": {"type": ["string", "null"]},
                "title": {"type": ["string", "null"]},
                "company": {"type": ["string", "null"]},
                "emails": {"type": "array", "items": {"type": "string"}},
                "phones": {"type": "array", "items": {"type": "string"}},
                "website": {"type": ["string", "null"]},
                "address": {"type": ["string", "null"]},
                "linkedin": {"type": ["string", "null"]},
                "social_media": {"type": "object"},
            },
        },
    ),
    TemplateType.ID_DOCUMENT: TemplateInfo(
        id=TemplateType.ID_DOCUMENT,
        name="ID Document",
        description="Extract data from passports, national IDs, driver's licenses.",
        example_fields=["full_name", "date_of_birth", "document_number", "expiry_date", "nationality"],
        output_schema={
            "type": "object",
            "properties": {
                "document_type": {"type": ["string", "null"]},
                "document_number": {"type": ["string", "null"]},
                "full_name": {"type": ["string", "null"]},
                "date_of_birth": {"type": ["string", "null"]},
                "place_of_birth": {"type": ["string", "null"]},
                "nationality": {"type": ["string", "null"]},
                "issue_date": {"type": ["string", "null"]},
                "expiry_date": {"type": ["string", "null"]},
                "issuing_authority": {"type": ["string", "null"]},
                "mrz": {"type": ["string", "null"]},
                "gender": {"type": ["string", "null"]},
                "address": {"type": ["string", "null"]},
            },
        },
    ),
    TemplateType.RESUME: TemplateInfo(
        id=TemplateType.RESUME,
        name="Resume / CV",
        description="Extract structured data from resumes and CVs.",
        example_fields=["name", "email", "experience", "education", "skills"],
        output_schema={
            "type": "object",
            "properties": {
                "full_name": {"type": ["string", "null"]},
                "email": {"type": ["string", "null"]},
                "phone": {"type": ["string", "null"]},
                "location": {"type": ["string", "null"]},
                "summary": {"type": ["string", "null"]},
                "experience": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "company": {"type": "string"},
                            "title": {"type": "string"},
                            "start_date": {"type": ["string", "null"]},
                            "end_date": {"type": ["string", "null"]},
                            "description": {"type": ["string", "null"]},
                        },
                    },
                },
                "education": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "institution": {"type": "string"},
                            "degree": {"type": ["string", "null"]},
                            "field": {"type": ["string", "null"]},
                            "graduation_year": {"type": ["string", "null"]},
                        },
                    },
                },
                "skills": {"type": "array", "items": {"type": "string"}},
                "languages": {"type": "array", "items": {"type": "string"}},
                "certifications": {"type": "array", "items": {"type": "string"}},
            },
        },
    ),
    TemplateType.MEDICAL_REPORT: TemplateInfo(
        id=TemplateType.MEDICAL_REPORT,
        name="Medical Report",
        description="Extract data from medical reports, lab results, prescriptions.",
        example_fields=["patient_name", "diagnosis", "medications", "lab_values", "doctor"],
        output_schema={
            "type": "object",
            "properties": {
                "report_type": {"type": ["string", "null"]},
                "report_date": {"type": ["string", "null"]},
                "patient_name": {"type": ["string", "null"]},
                "patient_dob": {"type": ["string", "null"]},
                "patient_id": {"type": ["string", "null"]},
                "doctor_name": {"type": ["string", "null"]},
                "facility": {"type": ["string", "null"]},
                "diagnoses": {"type": "array", "items": {"type": "string"}},
                "medications": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "dosage": {"type": ["string", "null"]},
                            "frequency": {"type": ["string", "null"]},
                        },
                    },
                },
                "lab_results": {"type": "object"},
                "notes": {"type": ["string", "null"]},
            },
        },
    ),
    TemplateType.TABLE_DATA: TemplateInfo(
        id=TemplateType.TABLE_DATA,
        name="Table Data",
        description="Extract all tabular data from images or documents.",
        example_fields=["tables", "headers", "rows"],
        output_schema={
            "type": "object",
            "properties": {
                "tables": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "title": {"type": ["string", "null"]},
                            "headers": {"type": "array", "items": {"type": "string"}},
                            "rows": {"type": "array", "items": {"type": "array"}},
                            "summary": {"type": ["string", "null"]},
                        },
                    },
                },
            },
        },
    ),
    TemplateType.CHART_DATA: TemplateInfo(
        id=TemplateType.CHART_DATA,
        name="Chart / Graph Data",
        description="Extract data series and labels from charts and graphs.",
        example_fields=["chart_type", "title", "x_axis", "y_axis", "series"],
        output_schema={
            "type": "object",
            "properties": {
                "chart_type": {"type": ["string", "null"]},
                "title": {"type": ["string", "null"]},
                "x_axis_label": {"type": ["string", "null"]},
                "y_axis_label": {"type": ["string", "null"]},
                "series": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": ["string", "null"]},
                            "data_points": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "x": {},
                                        "y": {},
                                    },
                                },
                            },
                        },
                    },
                },
                "annotations": {"type": "array", "items": {"type": "string"}},
            },
        },
    ),
    TemplateType.PRODUCT_LABEL: TemplateInfo(
        id=TemplateType.PRODUCT_LABEL,
        name="Product Label",
        description="Extract product information from labels and packaging.",
        example_fields=["product_name", "brand", "ingredients", "nutrition", "barcode"],
        output_schema={
            "type": "object",
            "properties": {
                "product_name": {"type": ["string", "null"]},
                "brand": {"type": ["string", "null"]},
                "sku": {"type": ["string", "null"]},
                "barcode": {"type": ["string", "null"]},
                "net_weight": {"type": ["string", "null"]},
                "ingredients": {"type": ["string", "null"]},
                "allergens": {"type": "array", "items": {"type": "string"}},
                "nutrition_facts": {"type": "object"},
                "certifications": {"type": "array", "items": {"type": "string"}},
                "country_of_origin": {"type": ["string", "null"]},
                "storage_instructions": {"type": ["string", "null"]},
                "expiry_date": {"type": ["string", "null"]},
            },
        },
    ),
    TemplateType.CONTRACT: TemplateInfo(
        id=TemplateType.CONTRACT,
        name="Contract",
        description="Extract key terms and parties from contracts.",
        example_fields=["parties", "effective_date", "term", "payment_terms", "key_clauses"],
        output_schema={
            "type": "object",
            "properties": {
                "contract_type": {"type": ["string", "null"]},
                "title": {"type": ["string", "null"]},
                "effective_date": {"type": ["string", "null"]},
                "expiry_date": {"type": ["string", "null"]},
                "parties": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "role": {"type": ["string", "null"]},
                            "address": {"type": ["string", "null"]},
                        },
                    },
                },
                "payment_terms": {"type": ["string", "null"]},
                "governing_law": {"type": ["string", "null"]},
                "key_obligations": {"type": "array", "items": {"type": "string"}},
                "termination_clauses": {"type": "array", "items": {"type": "string"}},
            },
        },
    ),
    TemplateType.FORM: TemplateInfo(
        id=TemplateType.FORM,
        name="Form",
        description="Extract filled form fields from any form document.",
        example_fields=["fields", "form_title", "submission_date"],
        output_schema={
            "type": "object",
            "properties": {
                "form_title": {"type": ["string", "null"]},
                "form_id": {"type": ["string", "null"]},
                "fields": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "label": {"type": "string"},
                            "value": {},
                            "field_type": {"type": ["string", "null"]},
                        },
                    },
                },
                "checkboxes": {"type": "object"},
                "signatures_present": {"type": "boolean"},
                "date_filled": {"type": ["string", "null"]},
            },
        },
    ),
}
