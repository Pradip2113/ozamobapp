import json
import os
import calendar
import frappe
from frappe import _
from hrms.hr.doctype.leave_application.leave_application import (
            get_leave_balance_on,
        )
from bs4 import BeautifulSoup
from frappe.utils import cstr, now, today
from frappe.auth import LoginManager
from frappe.permissions import has_permission
from frappe.utils import (
    cstr,
    get_date_str,
    today,
    nowdate,
    getdate,
    now_datetime,
    get_first_day,
    get_last_day,
    date_diff,
    flt,
    pretty_date,
    fmt_money,
)
from frappe.utils.data import nowtime
from ozamobapp.mobile_env.app_utils import (
    gen_response,
    generate_key,
    role_profile,
    ess_validate,
    get_employee_by_user,
    validate_employee_data,
    get_ess_settings,
    get_global_defaults,
    exception_handel,
)

from erpnext.accounts.utils import get_fiscal_year

@frappe.whitelist(allow_guest=True)
def login(usr, pwd):
    try:
        login_manager = LoginManager()
        login_manager.authenticate(usr, pwd)
        # validate_employee(login_manager.user)
        login_manager.post_login()
        if frappe.response["message"] == "Logged In":
            emp_data = get_employee_by_user(login_manager.user)
            frappe.response["user"] = login_manager.user
            frappe.response["key_details"] = generate_key(login_manager.user)
            # frappe.response["employee_id"] = emp_data.get("name")
        gen_response(200, frappe.response["message"])
    except frappe.AuthenticationError:
        gen_response(500, frappe.response["message"])
    except Exception as e:
        return exception_handel(e)


def validate_employee(user):
    if not frappe.db.exists("Employee", dict(user_id=user)):
        frappe.response["message"] = "Please link Employee with this user"
        raise frappe.AuthenticationError(frappe.response["message"])


@frappe.whitelist()
def get_user_document():
    user_doc = frappe.get_doc("User", frappe.session.user)
    return user_doc

@frappe.whitelist()
def user_has_permission():
    permission_list=[]
    doclist=["sales Invoice","Sales Order","Lead","Quotation","Leave Application","Expense Claim","Attendance","Customer"]
    for i in doclist:
        permission=has_permission(i)
        if permission:
            permission_list.append(i)
    return permission_list

@frappe.whitelist()
def add_comment(reference_doctype=None, reference_name=None, content=None):
    try:
        from frappe.desk.form.utils import add_comment

        comment_by = frappe.db.get_value(
            "User", frappe.session.user, "full_name", as_dict=1
        )
        add_comment(
            reference_doctype=reference_doctype,
            reference_name=reference_name,
            content=content,
            comment_email=frappe.session.user,
            comment_by=comment_by.get("full_name"),
        )
        return gen_response(200, "Comment Added Successfully")

    except Exception as e:
        return exception_handel(e)


@frappe.whitelist()
def get_dashboard():
    try:
        emp_data = get_employee_by_user(frappe.session.user, fields=["name", "company","employee_name"])
        if isinstance(emp_data, str):
            return gen_response(400,emp_data)
        attendance_details = get_attendance_details(emp_data)
        log_details = get_last_log_details(emp_data.get("name"))
        a,b=get_leave_balance_dashboard()
        current_site=frappe.local.site
        permissionlist=user_has_permission()
        dashboard_data = {
           "leave_balance": b,
            "permission_list":permissionlist,
            "last_log_type": log_details.get("log_type"),
           "attendance_details":attendance_details,
            "emp_name":emp_data.get("employee_name"),
            "email":frappe.session.user,
            "company": emp_data.get("company") or "Employee Dashboard",
            "last_log_time": log_details.get("time").strftime("%I:%M%p")
            if log_details.get("time")
            else "",
        }
        str1=frappe.get_cached_value(
            "Employee", emp_data.get("name"), "image"
        )
       
        if str1 is not None:
            dashboard_data["employee_image"] = frappe.utils.get_url() + str1
        else:
            dashboard_data["employee_image"] = None
            
        get_last_log_type(dashboard_data, emp_data.get("name"))
        return gen_response(200, "Dashboard data get successfully", dashboard_data)

    except Exception as e:
        return exception_handel(e)

@frappe.whitelist()
def download_pdf(doctype, name, format=None, doc=None, no_letterhead=0):
    from frappe.utils.pdf import get_pdf, cleanup

    html = frappe.get_print(doctype, name, format, doc=doc, no_letterhead=no_letterhead)
    frappe.local.response.filename = "{name}.pdf".format(
        name=name.replace(" ", "-").replace("/", "-")
    )
    frappe.local.response.filecontent = get_pdf(html)
    frappe.local.response.type = "download"

@frappe.whitelist()
def get_emp_name():
    try:
        emp_data = frappe.get_doc("User",frappe.session.user)
        global_defaults = get_global_defaults()
        company = global_defaults.get("default_company")
        dashboard_data = {
          
            "emp_name":emp_data.full_name,
            "email":emp_data.email,
            "company": company if company else None,
        }
        str1=frappe.get_cached_value(
            "User",frappe.session.user, "user_image",
        )
       
        if str1 is not None:
            dashboard_data["employee_image"] = frappe.utils.get_url()+ str1
        else:
            dashboard_data["employee_image"] = None
        return gen_response(200, "Dashboard data get successfully", dashboard_data)

    except Exception as e:
        return exception_handel(e)


def get_last_log_details(employee):
    log_details = frappe.db.sql(
        """select log_type,time from `tabEmployee Checkin` where employee=%s and DATE(time)=%s order by time desc""",
        (employee, today()),
        as_dict=1,
    )

    if log_details:
        return log_details[0]
    else:
        return {"log_type": "OUT", "time": None}


@frappe.whitelist()
def change_password(**kwargs):
    try:
        from frappe.utils.password import check_password, update_password
        data=kwargs
        user = frappe.session.user
        current_password = data.get("current_password")
        new_password = data.get("new_password")
        check_password(user, current_password)
        update_password(user, new_password)
        return gen_response(200, "Password updated")
    except frappe.AuthenticationError:
        return gen_response(500, "Incorrect current password")
    except Exception as e:
        return exception_handel(e)


@frappe.whitelist()
def get_profile():
    try:
        emp_data = get_employee_by_user(frappe.session.user)
        if isinstance(emp_data, str):
            return gen_response(400,emp_data)
        employee_details = frappe.get_cached_value(
            "Employee",
            emp_data.get("name"),
            [
                "employee_name",
                "designation",
                "name",
                "date_of_joining",
                "date_of_birth",
                "gender",
                "company_email",
                "personal_email",
                "cell_number",
                "emergency_phone_number",
            ],
            as_dict=True,
        )
        employee_details["date_of_joining"] = employee_details[
            "date_of_joining"
        ].strftime("%d-%m-%Y")
        employee_details["date_of_birth"] = employee_details["date_of_birth"].strftime(
            "%d-%m-%Y"
        )
        image=frappe.get_cached_value(
            "Employee", emp_data.get("name"), "image"
        )
        if image is not None:
            employee_details["employee_image"] = frappe.utils.get_url()+ image
        else:
            employee_details["employee_image"] = None
        

        return gen_response(200, "My Profile", employee_details)
    except Exception as e:
        return exception_handel(e)

@frappe.whitelist()
def update_profile_picture():
    try:
        emp_data = get_employee_by_user(frappe.session.user)
        if isinstance(emp_data, str):
            return gen_response(400,emp_data)
        from frappe.handler import upload_file

        employee_profile_picture = upload_file()
        employee_profile_picture.attached_to_doctype = "Employee"
        employee_profile_picture.attached_to_name = emp_data.get("name")
        employee_profile_picture.attached_to_field = "image"
        employee_profile_picture.save(ignore_permissions=True)

        frappe.db.set_value(
            "Employee", emp_data.get("name"), "image", employee_profile_picture.file_url
        )
        if employee_profile_picture:
            frappe.db.set_value(
                "User",
                frappe.session.user,
                "user_image",
                employee_profile_picture.file_url,
            )
        return gen_response(200, "Employee profile picture updated successfully")
    except Exception as e:
        return exception_handel(e)

@frappe.whitelist()
def edit_note_in_lead(doc_name, note, row_id):
    doc=frappe.get_doc("Lead",{'name':doc_name},['notes'])
    for d in doc.notes:
        if cstr(d.name) == row_id:
            d.note = note
            d.db_update()

