"""
Lightweight i18n for candidate-facing pages. No external dependency -
just a dict lookup + session-based language switch. Missing keys fall
back to English. Add more keys here as more pages get translated.
"""

from flask import session

DEFAULT_LANGUAGE = "en"
SUPPORTED_LANGUAGES = {"en": "English", "hi": "हिन्दी"}

TRANSLATIONS = {
    "en": {
        "candidate_portal": "Candidate Portal",
        "portal_subtitle": "Codevocado Placement Tracking",
        "login_title": "Candidate Login",
        "registration_number": "Registration Number",
        "password": "Password",
        "login_button": "Login",
        "login_help_text": "Default password is your registered mobile number. Contact your training center if you need help.",

        "welcome": "Welcome,",
        "registration_no_label": "Registration No:",
        "logout": "Logout",

        "my_details_readonly": "My Details (read-only)",
        "fathers_name": "Father's Name",
        "date_of_birth": "Date of Birth",
        "aadhaar": "Aadhaar",
        "training_center": "Training Center",
        "course": "Course",
        "training_status": "Training Status",
        "verification_status": "Verification Status",
        "employer": "Employer",
        "readonly_note": "These fields are managed by your training center. Contact them for corrections.",

        "update_contact_bank": "Update Contact & Bank Details",
        "mobile": "Mobile",
        "alternative_mobile": "Alternative Mobile",
        "email": "Email",
        "current_address": "Current Address",
        "permanent_address": "Permanent Address",
        "bank_name": "Bank Name",
        "account_number": "Account Number",
        "ifsc": "IFSC Code",
        "save_changes": "Save Changes",

        "change_password": "Change Password",
        "current_password": "Current Password",
        "new_password": "New Password",
        "confirm_new_password": "Confirm New Password",

        "feedback_prompt_title": "How was your placement experience?",
        "feedback_prompt_body": "You've been placed! We'd love to hear your feedback.",
        "feedback_rating_label": "Rate your experience",
        "feedback_comment_label": "Additional comments (optional)",
        "feedback_submit": "Submit Feedback",
        "feedback_thanks": "Thank you for your feedback!",
        "feedback_already_submitted": "You've already submitted feedback. Thank you!",
    },
    "hi": {
        "candidate_portal": "उम्मीदवार पोर्टल",
        "portal_subtitle": "कोडवोकाडो प्लेसमेंट ट्रैकिंग",
        "login_title": "उम्मीदवार लॉगिन",
        "registration_number": "पंजीकरण नंबर",
        "password": "पासवर्ड",
        "login_button": "लॉगिन करें",
        "login_help_text": "डिफ़ॉल्ट पासवर्ड आपका पंजीकृत मोबाइल नंबर है। सहायता के लिए अपने प्रशिक्षण केंद्र से संपर्क करें।",

        "welcome": "स्वागत है,",
        "registration_no_label": "पंजीकरण संख्या:",
        "logout": "लॉगआउट",

        "my_details_readonly": "मेरी जानकारी (केवल पढ़ने योग्य)",
        "fathers_name": "पिता का नाम",
        "date_of_birth": "जन्म तिथि",
        "aadhaar": "आधार",
        "training_center": "प्रशिक्षण केंद्र",
        "course": "कोर्स",
        "training_status": "प्रशिक्षण स्थिति",
        "verification_status": "सत्यापन स्थिति",
        "employer": "नियोक्ता",
        "readonly_note": "ये फ़ील्ड आपके प्रशिक्षण केंद्र द्वारा प्रबंधित की जाती हैं। सुधार हेतु उनसे संपर्क करें।",

        "update_contact_bank": "संपर्क और बैंक विवरण अपडेट करें",
        "mobile": "मोबाइल",
        "alternative_mobile": "वैकल्पिक मोबाइल",
        "email": "ईमेल",
        "current_address": "वर्तमान पता",
        "permanent_address": "स्थायी पता",
        "bank_name": "बैंक का नाम",
        "account_number": "खाता संख्या",
        "ifsc": "IFSC कोड",
        "save_changes": "परिवर्तन सहेजें",

        "change_password": "पासवर्ड बदलें",
        "current_password": "वर्तमान पासवर्ड",
        "new_password": "नया पासवर्ड",
        "confirm_new_password": "नए पासवर्ड की पुष्टि करें",

        "feedback_prompt_title": "आपका प्लेसमेंट अनुभव कैसा रहा?",
        "feedback_prompt_body": "आपकी नियुक्ति हो चुकी है! हमें आपकी प्रतिक्रिया जानकर खुशी होगी।",
        "feedback_rating_label": "अपने अनुभव को रेट करें",
        "feedback_comment_label": "अतिरिक्त टिप्पणी (वैकल्पिक)",
        "feedback_submit": "प्रतिक्रिया भेजें",
        "feedback_thanks": "आपकी प्रतिक्रिया के लिए धन्यवाद!",
        "feedback_already_submitted": "आप पहले ही प्रतिक्रिया दे चुके हैं। धन्यवाद!",
    },
}


def get_current_language():
    return session.get("lang", DEFAULT_LANGUAGE)


def translate(key):
    lang = get_current_language()
    return TRANSLATIONS.get(lang, {}).get(key) or TRANSLATIONS[DEFAULT_LANGUAGE].get(key, key)