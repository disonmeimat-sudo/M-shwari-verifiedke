from datetime import datetime

from app.extensions import db


class PaymentTransaction(db.Model):
    __tablename__ = "payment_transactions"

    id = db.Column(db.Integer, primary_key=True)
    application_id = db.Column(
        db.Integer, db.ForeignKey("loan_applications.id"),
        nullable=False, index=True,
    )
    phone = db.Column(db.String(20), nullable=False)
    amount = db.Column(db.Integer, nullable=False)
    provider = db.Column(db.String(30), nullable=False, default="sandbox")
    reference = db.Column(db.String(120), unique=True, index=True, nullable=True)
    status = db.Column(db.String(30), nullable=False, default="PENDING", index=True)
    meta_data = db.Column(db.Text, nullable=True)  # provider payload, no secrets
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    application = db.relationship("LoanApplication", back_populates="transactions")