"""Rule-based page classification from DOM metadata."""


def classify_page(dom_elements: list, url: str = "", title: str = "") -> dict:
    """Classify page type and suggest actions from DOM elements.

    Returns:
        {
            "page_type": "login" | "signup" | "cookie_banner" | "captcha" | "search" | "content" | "error" | "unknown",
            "confidence": 0.0-1.0,
            "suggested_action": {"type": "click"|"fill"|"dismiss"|"abort"|"none", ...details},
            "detected_elements": {"login_form": bool, "cookie_banner": bool, "captcha": bool, ...}
        }
    """
    detected = {
        "login_form": False,
        "signup_form": False,
        "cookie_banner": False,
        "captcha": False,
        "search_input": False,
        "error_page": False,
    }

    cookie_button = None
    password_fields = []
    text_inputs = []
    checkboxes = []
    has_terms_checkbox = False
    search_input = None
    captcha_iframe = None

    title_lower = title.lower() if title else ""
    url_lower = url.lower() if url else ""

    # Scan elements
    for el in dom_elements:
        tag = el.get("tag", "").lower()
        text = el.get("text", "").lower()
        aria = el.get("ariaLabel", "").lower()
        placeholder = el.get("placeholder", "").lower()
        el_id = el.get("id", "").lower()
        el_class = el.get("class", "").lower() if el.get("class") else ""
        el_type = el.get("type", "").lower()
        el_name = el.get("name", "").lower()
        el_role = el.get("role", "").lower()
        el_src = el.get("src", "").lower() if el.get("src") else ""

        # Cookie banner detection
        cookie_keywords = ("accept", "cookie", "consent")
        cookie_class_keywords = ("cookie", "consent", "banner", "gdpr")
        is_cookie_text = any(k in text for k in cookie_keywords)
        is_cookie_class = any(k in el_class or k in el_id for k in cookie_class_keywords)

        if (is_cookie_text or is_cookie_class) and tag in ("button", "a", "div", "span"):
            if any(k in text for k in ("accept", "agree", "ok", "got it", "dismiss", "allow")):
                if cookie_button is None:
                    cookie_button = el
                detected["cookie_banner"] = True

        # Password fields
        if el_type == "password" or (tag == "input" and el_type == "password"):
            password_fields.append(el)

        # Text inputs
        if tag == "input" and el_type in ("text", "email", "tel", ""):
            text_inputs.append(el)

        # Checkboxes
        if tag == "input" and el_type == "checkbox":
            checkboxes.append(el)
            terms_words = ("terms", "agree", "accept", "privacy", "policy", "tos")
            if any(w in text or w in aria or w in el_name for w in terms_words):
                has_terms_checkbox = True

        # Search input
        if el_role == "search" or el_name == "q" or el_name == "query" or el_name == "search":
            search_input = el
            detected["search_input"] = True
        if tag == "input" and ("search" in el_type or "search" in placeholder):
            search_input = el
            detected["search_input"] = True

        # CAPTCHA iframes
        if tag == "iframe":
            captcha_hosts = ("captcha", "recaptcha", "hcaptcha", "funcaptcha", "arkoselabs")
            if any(h in el_src for h in captcha_hosts):
                captcha_iframe = el
                detected["captcha"] = True

    # Error page detection from title
    error_keywords = ("404", "500", "error", "not found", "page not found", "server error")
    if any(k in title_lower for k in error_keywords):
        detected["error_page"] = True

    # Login form: password field present with 0-2 text inputs (username/email + password)
    if password_fields and len(text_inputs) <= 2:
        detected["login_form"] = True

    # Signup form: multiple text inputs + password + terms checkbox
    if password_fields and len(text_inputs) >= 2 and (has_terms_checkbox or len(text_inputs) >= 3):
        detected["signup_form"] = True

    # Priority-based classification
    if detected["captcha"]:
        # Distinguish reCAPTCHA (solvable) from Arkose/hCaptcha (not solvable)
        captcha_type = "unknown"
        if captcha_iframe:
            src = captcha_iframe.get("src", "").lower() if captcha_iframe.get("src") else ""
            if "recaptcha" in src:
                captcha_type = "recaptcha"
            elif "arkoselabs" in src or "funcaptcha" in src:
                captcha_type = "arkose"
            elif "hcaptcha" in src:
                captcha_type = "hcaptcha"
        return {
            "page_type": "captcha",
            "confidence": 0.9,
            "suggested_action": {
                "type": "abort",
                "target": "CAPTCHA detected ({}) — will attempt auto-solve for reCAPTCHA".format(captcha_type),
            },
            "detected_elements": detected,
            "captcha_type": captcha_type,
        }

    if detected["cookie_banner"] and cookie_button:
        selector_hint = ""
        if cookie_button.get("id"):
            selector_hint = "#" + cookie_button["id"]
        return {
            "page_type": "cookie_banner",
            "confidence": 0.8,
            "suggested_action": {
                "type": "dismiss",
                "target": cookie_button.get("text", "accept button"),
                "selector_hint": selector_hint,
            },
            "detected_elements": detected,
        }

    if detected["error_page"]:
        return {
            "page_type": "error",
            "confidence": 0.85,
            "suggested_action": {"type": "abort", "target": title},
            "detected_elements": detected,
        }

    if detected["signup_form"]:
        return {
            "page_type": "signup",
            "confidence": 0.7,
            "suggested_action": {"type": "fill", "target": "signup form"},
            "detected_elements": detected,
        }

    if detected["login_form"]:
        return {
            "page_type": "login",
            "confidence": 0.8,
            "suggested_action": {"type": "fill", "target": "login form"},
            "detected_elements": detected,
        }

    if detected["search_input"] and search_input:
        selector_hint = ""
        if search_input.get("id"):
            selector_hint = "#" + search_input["id"]
        elif search_input.get("name"):
            sel_name = search_input["name"]
            selector_hint = "input[name=\"" + sel_name + "\"]"
        return {
            "page_type": "search",
            "confidence": 0.7,
            "suggested_action": {
                "type": "fill",
                "target": "search input",
                "selector_hint": selector_hint,
            },
            "detected_elements": detected,
        }

    # Default: content page
    return {
        "page_type": "content" if dom_elements else "unknown",
        "confidence": 0.4 if dom_elements else 0.1,
        "suggested_action": {"type": "none"},
        "detected_elements": detected,
    }
