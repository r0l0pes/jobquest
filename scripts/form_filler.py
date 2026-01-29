#!/usr/bin/env python3
"""
Generic ATS form filler using Playwright.
Detects form fields generically (not platform-specific), fills them, uploads resume.
NEVER auto-submits - pauses with browser open for user review.
Outputs JSON report to stdout, status to stderr.
"""

import sys
import os
import json
import argparse
import time
import re

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from playwright.sync_api import sync_playwright


# Field classification patterns
FIELD_PATTERNS = {
    "name": re.compile(
        r"\b(full.?name|your.?name|candidate.?name|applicant.?name|first.?name.*last.?name)\b",
        re.IGNORECASE,
    ),
    "first_name": re.compile(r"\b(first.?name|given.?name|fname)\b", re.IGNORECASE),
    "last_name": re.compile(r"\b(last.?name|sur.?name|family.?name|lname)\b", re.IGNORECASE),
    "email": re.compile(r"\b(e-?mail|email.?address)\b", re.IGNORECASE),
    "phone": re.compile(r"\b(phone|telephone|mobile|cell|tel)\b", re.IGNORECASE),
    "linkedin": re.compile(r"\b(linkedin|linked.?in)\b", re.IGNORECASE),
    "location": re.compile(r"\b(location|city|address|where.?are.?you)\b", re.IGNORECASE),
    "website": re.compile(r"\b(website|portfolio|personal.?url|blog)\b", re.IGNORECASE),
    "cover_letter": re.compile(r"\b(cover.?letter|motivation|comments|additional.?info)\b", re.IGNORECASE),
    "salary": re.compile(r"\b(salary|compensation|pay.?expect)\b", re.IGNORECASE),
    "start_date": re.compile(r"\b(start.?date|avail|earliest|when.?can.?you)\b", re.IGNORECASE),
    "company_current": re.compile(r"\b(current.?company|current.?employer|org)\b", re.IGNORECASE),
    "title_current": re.compile(r"\b(current.?title|job.?title|position)\b", re.IGNORECASE),
}


def classify_field(label_text, name_attr, placeholder, field_id):
    """Classify a form field based on its label, name attribute, placeholder, and id."""
    search_text = " ".join(filter(None, [label_text, name_attr, placeholder, field_id]))
    if not search_text.strip():
        return "unknown"

    for field_type, pattern in FIELD_PATTERNS.items():
        if pattern.search(search_text):
            return field_type

    return "unknown"


def get_field_label(page, element):
    """Try to find the label text for a form element."""
    # Method 1: aria-label
    aria = element.get_attribute("aria-label")
    if aria:
        return aria

    # Method 2: associated <label> via for=id
    field_id = element.get_attribute("id")
    if field_id:
        label = page.query_selector(f'label[for="{field_id}"]')
        if label:
            return label.inner_text().strip()

    # Method 3: parent label
    parent_label = element.evaluate(
        """el => {
            let parent = el.closest('label');
            if (parent) return parent.innerText.trim();
            // Check previous sibling or parent div for label-like text
            let prev = el.previousElementSibling;
            if (prev && (prev.tagName === 'LABEL' || prev.tagName === 'SPAN' || prev.tagName === 'DIV')) {
                return prev.innerText.trim();
            }
            // Check parent for label-like child
            let parentDiv = el.parentElement;
            if (parentDiv) {
                let label = parentDiv.querySelector('label, .label, [class*="label"]');
                if (label && label !== el) return label.innerText.trim();
            }
            return '';
        }"""
    )
    if parent_label:
        return parent_label

    return ""


def scan_form_fields(page):
    """Scan page for all form fields and classify them."""
    fields = []

    # Scan inputs (exclude hidden, submit, button, file)
    inputs = page.query_selector_all(
        'input:not([type="hidden"]):not([type="submit"]):not([type="button"]):not([type="file"]):not([type="checkbox"]):not([type="radio"])'
    )
    for inp in inputs:
        if not inp.is_visible():
            continue
        label = get_field_label(page, inp)
        name = inp.get_attribute("name") or ""
        placeholder = inp.get_attribute("placeholder") or ""
        field_id = inp.get_attribute("id") or ""
        field_type = classify_field(label, name, placeholder, field_id)

        fields.append({
            "element": inp,
            "tag": "input",
            "input_type": inp.get_attribute("type") or "text",
            "label": label,
            "name": name,
            "placeholder": placeholder,
            "id": field_id,
            "classified_as": field_type,
        })

    # Scan textareas
    textareas = page.query_selector_all("textarea")
    for ta in textareas:
        if not ta.is_visible():
            continue
        label = get_field_label(page, ta)
        name = ta.get_attribute("name") or ""
        placeholder = ta.get_attribute("placeholder") or ""
        field_id = ta.get_attribute("id") or ""
        field_type = classify_field(label, name, placeholder, field_id)

        fields.append({
            "element": ta,
            "tag": "textarea",
            "input_type": "textarea",
            "label": label,
            "name": name,
            "placeholder": placeholder,
            "id": field_id,
            "classified_as": field_type,
        })

    # Scan selects
    selects = page.query_selector_all("select")
    for sel in selects:
        if not sel.is_visible():
            continue
        label = get_field_label(page, sel)
        name = sel.get_attribute("name") or ""
        field_id = sel.get_attribute("id") or ""
        field_type = classify_field(label, name, "", field_id)

        # Get options
        options = sel.query_selector_all("option")
        option_values = []
        for opt in options:
            val = opt.get_attribute("value") or ""
            text = opt.inner_text().strip()
            if val or text:
                option_values.append({"value": val, "text": text})

        fields.append({
            "element": sel,
            "tag": "select",
            "input_type": "select",
            "label": label,
            "name": name,
            "placeholder": "",
            "id": field_id,
            "classified_as": field_type,
            "options": option_values,
        })

    return fields


def fill_fields(page, fields, data):
    """Fill form fields with provided data. Returns report of filled/skipped/unknown."""
    report = {"filled": [], "skipped": [], "unknown": []}

    for field in fields:
        classification = field["classified_as"]
        element = field["element"]
        value = data.get(classification)

        # Also check by field name or id for custom data keys
        if not value and field["name"]:
            value = data.get(field["name"])
        if not value and field["id"]:
            value = data.get(field["id"])

        field_info = {
            "label": field["label"],
            "name": field["name"],
            "id": field["id"],
            "classified_as": classification,
            "tag": field["tag"],
        }
        if field["tag"] == "select":
            field_info["options"] = field.get("options", [])

        if classification == "unknown" and not value:
            report["unknown"].append(field_info)
            continue

        if not value:
            report["skipped"].append(field_info)
            continue

        try:
            if field["tag"] == "select":
                # Try to match by value or text
                element.select_option(value=value)
                report["filled"].append({**field_info, "value": value})
            else:
                element.fill(value)
                report["filled"].append({**field_info, "value": value})
            print(f"  Filled: {field['label'] or field['name'] or field['id']} = {value[:30]}...", file=sys.stderr)
        except Exception as e:
            field_info["error"] = str(e)
            report["skipped"].append(field_info)
            print(f"  Failed: {field['label'] or field['name']} - {e}", file=sys.stderr)

    return report


def find_apply_button(page):
    """Find and click 'Apply' / 'Apply Now' / 'Apply for this job' button."""
    apply_patterns = [
        "a:has-text('Apply for this job')",
        "a:has-text('Apply Now')",
        "a:has-text('Apply')",
        "button:has-text('Apply for this job')",
        "button:has-text('Apply Now')",
        "button:has-text('Apply')",
    ]
    for selector in apply_patterns:
        try:
            btn = page.query_selector(selector)
            if btn and btn.is_visible():
                print(f"Clicking apply button: {btn.inner_text().strip()}", file=sys.stderr)
                btn.click()
                page.wait_for_load_state("domcontentloaded")
                time.sleep(2)
                return True
        except Exception:
            continue
    return False


def find_next_button(page):
    """Find 'Next' / 'Continue' button for multi-page forms."""
    next_patterns = [
        "button:has-text('Next')",
        "button:has-text('Continue')",
        "input[type='submit'][value*='Next']",
        "input[type='submit'][value*='Continue']",
    ]
    for selector in next_patterns:
        try:
            btn = page.query_selector(selector)
            if btn and btn.is_visible():
                return btn
        except Exception:
            continue
    return None


def upload_resume(page, resume_path):
    """Find file input and upload resume."""
    file_inputs = page.query_selector_all('input[type="file"]')
    for fi in file_inputs:
        try:
            fi.set_input_files(resume_path)
            print(f"Uploaded resume: {resume_path}", file=sys.stderr)
            return True
        except Exception as e:
            print(f"Upload attempt failed: {e}", file=sys.stderr)
    return False


def run_form_filler(url, resume_pdf, data):
    """Main form filling logic."""
    all_reports = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()

        print(f"Navigating to {url}...", file=sys.stderr)
        page.goto(url, wait_until="domcontentloaded")
        time.sleep(3)

        # Try clicking apply button if on description page
        find_apply_button(page)
        time.sleep(2)

        # Upload resume if provided
        resume_uploaded = False
        if resume_pdf and os.path.exists(resume_pdf):
            resume_uploaded = upload_resume(page, resume_pdf)

        # Fill form pages (handle multi-page)
        page_num = 1
        while True:
            print(f"\n--- Form Page {page_num} ---", file=sys.stderr)

            # Scan and fill fields
            fields = scan_form_fields(page)
            report = fill_fields(page, fields, data)
            report["page"] = page_num
            all_reports.append(report)

            # Check for resume upload on this page too
            if resume_pdf and not resume_uploaded:
                resume_uploaded = upload_resume(page, resume_pdf)

            # Look for Next/Continue button
            next_btn = find_next_button(page)
            if next_btn:
                print("Found 'Next' button, advancing...", file=sys.stderr)
                next_btn.click()
                page.wait_for_load_state("domcontentloaded")
                time.sleep(2)
                page_num += 1
            else:
                break

        # Compile final result
        result = {
            "url": url,
            "resume_uploaded": resume_uploaded,
            "pages_filled": page_num,
            "reports": [],
        }

        # Strip non-serializable elements from reports
        for r in all_reports:
            result["reports"].append({
                "page": r["page"],
                "filled": r["filled"],
                "skipped": r["skipped"],
                "unknown": r["unknown"],
            })

        total_filled = sum(len(r["filled"]) for r in all_reports)
        total_skipped = sum(len(r["skipped"]) for r in all_reports)
        total_unknown = sum(len(r["unknown"]) for r in all_reports)

        result["summary"] = {
            "total_filled": total_filled,
            "total_skipped": total_skipped,
            "total_unknown": total_unknown,
        }

        print(json.dumps(result, indent=2))

        # NEVER auto-submit - pause for user review
        print("\n" + "=" * 50, file=sys.stderr)
        print("REVIEW THE FORM IN THE BROWSER", file=sys.stderr)
        print("1. Verify all fields are correct", file=sys.stderr)
        print("2. Fill any remaining fields manually", file=sys.stderr)
        print("3. Solve any CAPTCHA", file=sys.stderr)
        print("4. Submit when ready", file=sys.stderr)
        print("=" * 50, file=sys.stderr)

        try:
            input("Press Enter to close the browser...")
        except EOFError:
            # Running without interactive stdin (e.g. from Claude Code)
            # Keep browser open until user closes it manually
            print("Browser will stay open. Close it manually when done.", file=sys.stderr)
            try:
                page.wait_for_event("close", timeout=0)
            except Exception:
                pass
        browser.close()


def main():
    parser = argparse.ArgumentParser(description="Generic ATS form filler")
    parser.add_argument("--url", required=True, help="Application URL")
    parser.add_argument("--resume-pdf", help="Path to resume PDF")
    parser.add_argument("--data-file", help="Path to JSON file with form data")
    args = parser.parse_args()

    # Load form data
    data = {}
    if args.data_file and os.path.exists(args.data_file):
        with open(args.data_file) as f:
            data = json.load(f)
    else:
        # Default data from config
        from config import (
            APPLICANT_NAME, APPLICANT_EMAIL, APPLICANT_PHONE,
            APPLICANT_LINKEDIN, APPLICANT_LOCATION,
        )
        name_parts = APPLICANT_NAME.split() if APPLICANT_NAME else ["", ""]
        data = {
            "name": APPLICANT_NAME,
            "first_name": name_parts[0] if name_parts else "",
            "last_name": name_parts[-1] if len(name_parts) > 1 else "",
            "email": APPLICANT_EMAIL,
            "phone": APPLICANT_PHONE,
            "linkedin": APPLICANT_LINKEDIN,
            "location": APPLICANT_LOCATION,
        }

    run_form_filler(args.url, args.resume_pdf, data)


if __name__ == "__main__":
    main()
