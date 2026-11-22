from django.contrib.auth.models import AbstractUser, UserManager as DjangoUserManager
from django.db import models


class UserManager(DjangoUserManager):
    def create_superuser(self, username, email=None, password=None, **extra_fields):
        extra_fields.setdefault("role", User.Role.ADMIN)
        extra_fields.setdefault("approval_status", User.Approval.APPROVED)
        return super().create_superuser(username, email, password, **extra_fields)


class User(AbstractUser):
    """Custom user with a single role and an approval status.

    Consumers / regulators deliberately have *no* account: they use the public
    QR verification pages.

    Approval mechanism
    ------------------
    * Staff roles (admin, lab, processor, manufacturer) are created only by an
      administrator and are APPROVED immediately.
    * Farmers / wild collectors may self-register. Their account starts as
      PENDING and they cannot log in until an administrator APPROVES it.
    """

    class Role(models.TextChoices):
        ADMIN = "ADMIN", "Administrator"
        FARMER = "FARMER", "Farmer / Wild Collector"
        LAB = "LAB", "Laboratory Personnel"
        PROCESSOR = "PROCESSOR", "Processor"
        MANUFACTURER = "MANUFACTURER", "Manufacturer"

    class Approval(models.TextChoices):
        PENDING = "PENDING", "Pending approval"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"

    email = models.EmailField("email address", unique=True)
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.FARMER, db_index=True)
    approval_status = models.CharField(
        max_length=10, choices=Approval.choices, default=Approval.APPROVED, db_index=True
    )
    phone = models.CharField(max_length=20, blank=True)
    organization = models.CharField(max_length=150, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, null=True)

    objects = UserManager()
    REQUIRED_FIELDS = ["email"]

    class Meta:
        ordering = ["username"]

    def __str__(self):
        return self.display_name

    @property
    def display_name(self) -> str:
        return self.get_full_name().strip() or self.username

    @property
    def effective_role(self) -> str:
        """Superusers are always treated as administrators."""
        return self.Role.ADMIN if self.is_superuser else self.role

    @property
    def is_admin_role(self) -> bool:
        return self.effective_role == self.Role.ADMIN

    @property
    def is_approved(self) -> bool:
        return self.approval_status == self.Approval.APPROVED
