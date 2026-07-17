INTENTS = [
    "ASK_OPERATING_HOURS", "ASK_DEPARTMENT_LOCATION", "ASK_SERVICE_PRICE",
    "ASK_PREPARATION_INSTRUCTION", "FIND_SPECIALTY", "FIND_DOCTOR",
    "BOOK_APPOINTMENT", "RESCHEDULE_APPOINTMENT", "CANCEL_APPOINTMENT",
    "CHECK_APPOINTMENT", "CHECK_QUEUE", "CHECK_INSURANCE", "CHECK_PAYMENT",
    "CHECK_RESULT_STATUS", "REQUEST_HUMAN_AGENT", "SUBMIT_COMPLAINT",
    "EMERGENCY_SYMPTOM", "MEDICAL_DIAGNOSIS_REQUEST", "PRESCRIPTION_REQUEST", "OUT_OF_SCOPE",
]
ENTITY_TYPES = [
    "facility", "department", "specialty", "service", "doctor", "appointment_date",
    "appointment_time", "patient_name", "patient_code", "phone_number", "date_of_birth",
    "insurance_type", "payment_method", "symptom", "age_group", "preferred_language",
]
TOOLS = [
    "search_services", "search_doctors", "get_available_slots", "hold_appointment_slot",
    "release_appointment_slot", "create_appointment", "reschedule_appointment",
    "cancel_appointment", "verify_patient_identity", "check_insurance", "get_invoice",
    "get_payment_status", "get_result_status", "create_support_ticket", "send_notification",
]
SCENARIOS = ["SUCCESS", "MISSING_INFORMATION", "BUSINESS_CONFLICT", "SYSTEM_ERROR", "SAFETY_PRIVACY"]

