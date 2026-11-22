from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.core.testing import PASSWORD, make_user

HOMES = {
    "ADMIN": "accounts:admin_dashboard", "FARMER": "traceability:farmer_dashboard",
    "LAB": "laboratory:dashboard", "PROCESSOR": "processing:dashboard",
    "MANUFACTURER": "manufacturing:dashboard",
}


class LoginTests(TestCase):
    def test_login_redirects_each_role_to_own_dashboard(self):
        for role, name in HOMES.items():
            user = make_user(role)
            resp = self.client.post(reverse("accounts:login"), {"username": user.username, "password": PASSWORD}, follow=True)
            self.assertEqual(resp.redirect_chain[-1][0], reverse(name), role)
            self.client.logout()

    def test_login_with_email(self):
        user = make_user("LAB", email="lab@example.com")
        self.assertTrue(self.client.login(username="lab@example.com", password=PASSWORD))

    def test_wrong_password_rejected(self):
        user = make_user("LAB")
        resp = self.client.post(reverse("accounts:login"), {"username": user.username, "password": "nope"})
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_passwords_are_hashed(self):
        self.assertTrue(make_user().password.startswith("pbkdf2_"))

    def test_pending_farmer_cannot_login(self):
        user = make_user("FARMER", approval=User.Approval.PENDING)
        resp = self.client.post(reverse("accounts:login"), {"username": user.username, "password": PASSWORD})
        self.assertContains(resp, "waiting for administrator approval")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_logout(self):
        user = make_user("LAB"); self.client.force_login(user)
        self.client.post(reverse("accounts:logout"))
        self.assertNotIn("_auth_user_id", self.client.session)


class RoleAccessTests(TestCase):
    PROTECTED = {
        "ADMIN": ["/accounts/admin-dashboard/", "/accounts/users/", "/manage/herbs/", "/manage/regions/",
                  "/trace/batches/", "/trace/ledger/", "/trace/reports/"],
        "FARMER": ["/trace/farmer/", "/trace/collections/new/", "/trace/collections/mine/"],
        "LAB": ["/lab/", "/lab/queue/", "/lab/history/"],
        "PROCESSOR": ["/processing/", "/processing/batches/", "/processing/history/"],
        "MANUFACTURER": ["/manufacturing/", "/manufacturing/new/", "/manufacturing/history/"],
    }

    def test_anonymous_redirected_to_login(self):
        for paths in self.PROTECTED.values():
            for p in paths:
                resp = self.client.get(p)
                self.assertEqual(resp.status_code, 302, p)
                self.assertIn("/accounts/login/", resp["Location"])

    def test_each_role_can_open_own_pages_and_gets_403_elsewhere(self):
        for role, own in self.PROTECTED.items():
            self.client.force_login(make_user(role))
            for r, paths in self.PROTECTED.items():
                for p in paths:
                    code = self.client.get(p).status_code
                    self.assertEqual(code, 200 if r == role else 403, f"{role} -> {p} gave {code}")
            self.client.logout()

    def test_public_pages_need_no_login(self):
        for p in ["/", "/accounts/login/", "/accounts/register/", "/verify/"]:
            self.assertEqual(self.client.get(p).status_code, 200, p)


class RegistrationTests(TestCase):
    def test_public_registration_creates_pending_farmer_even_if_role_posted(self):
        self.client.post(reverse("accounts:register"), {
            "username": "newfarmer", "first_name": "N", "last_name": "F", "email": "nf@example.com",
            "password1": "Str0ng!Pass#99", "password2": "Str0ng!Pass#99", "role": "ADMIN",
            "approval_status": "APPROVED", "is_superuser": "on"})
        user = User.objects.get(username="newfarmer")
        self.assertEqual((user.role, user.approval_status), ("FARMER", "PENDING"))
        self.assertFalse(user.is_superuser)

    def test_admin_can_approve_and_create_staff(self):
        admin = make_user("ADMIN"); self.client.force_login(admin)
        pending = make_user("FARMER", approval=User.Approval.PENDING)
        self.client.post(reverse("accounts:user_approval", args=[pending.pk, "approve"]))
        pending.refresh_from_db(); self.assertTrue(pending.is_approved)
        self.client.post(reverse("accounts:user_create"), {
            "username": "labstaff", "first_name": "L", "last_name": "S", "email": "l@example.com",
            "role": "LAB", "approval_status": "APPROVED", "is_active": "on", "password": "Str0ng!Pass#99"})
        self.assertEqual(User.objects.get(username="labstaff").role, "LAB")

    def test_non_admin_cannot_approve(self):
        pending = make_user("FARMER", approval=User.Approval.PENDING)
        self.client.force_login(make_user("LAB"))
        resp = self.client.post(reverse("accounts:user_approval", args=[pending.pk, "approve"]))
        self.assertEqual(resp.status_code, 403)

    def test_approval_redirect_is_not_open(self):
        self.client.force_login(make_user("ADMIN"))
        pending = make_user("FARMER", approval=User.Approval.PENDING)
        resp = self.client.post(reverse("accounts:user_approval", args=[pending.pk, "approve"]),
                                {"next": "https://evil.example/"})
        self.assertEqual(resp["Location"], reverse("accounts:user_list"))
