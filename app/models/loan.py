from datetime import datetime

from app.extensions import db
from app.utils import generate_application_number


class LoanApplication(db.Model):
    __tablename__ = "loan_applications"

    id = db.Column(db.Integer, primary_key=True)
    application_number = db.Column(
        db.String(40), unique=True, index=True,
        default=generate_application_number,
    )
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    loan_amount = db.Column(db.Integer, nullable=False)
    service_fee = db.Column(db.Integer, nullable=False)
    total_amount = db.Column(db.Integer, nullable=False)
    full_name = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(20), nullable=False, index=True)
    county = db.Column(db.String(60), nullable=False)
    loan_reason = db.Column(db.String(40), nullable=False)
    email = db.Column(db.String(120), nullable=True)
    status = db.Column(db.String(30), nullable=False, default="DRAFT", index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    user = db.relationship("User", back_populates="applications")
    transactions = db.relationship(
        "PaymentTransaction", back_populates="application",
        order_by="PaymentTransaction.created_at.desc()",
    )

    def latest_transaction(self):
        return self.transactions[0] if self.transactions else None


class Notification(db.Model):
    __tablename__ = "notifications"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    application_id = db.Column(
        db.Integer, db.ForeignKey("loan_applications.id"), nullable=True
    )
    title = db.Column(db.String(120), nullable=False)
    body = db.Column(db.Text, nullable=True)
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)