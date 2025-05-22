from . import db
# from flask_login import UserMixin # Убираем UserMixin

class Faculty(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), nullable=False)
    short_name = db.Column(db.String(32), nullable=False)
    description = db.Column(db.Text)
    groups = db.relationship('Group', backref='faculty', cascade='all, delete-orphan')

class Group(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    year = db.Column(db.Integer, nullable=False)
    duration = db.Column(db.Integer, nullable=False)
    name = db.Column(db.String(64), nullable=False)
    course = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(32))
    faculty_id = db.Column(db.Integer, db.ForeignKey('faculty.id'), nullable=False)
    students = db.relationship('Student', backref='group', cascade='all, delete-orphan')

class Student(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(100), nullable=False)
    date_of_birth = db.Column(db.Date, nullable=False)
    phone_number = db.Column(db.String(32), nullable=False)
    email = db.Column(db.String(128), nullable=False, unique=True)
    group_id = db.Column(db.Integer, db.ForeignKey('group.id'), nullable=False)

# class User(UserMixin, db.Model): # Комментируем или удаляем модель User
#     id = db.Column(db.Integer, primary_key=True)
#     username = db.Column(db.String(64), unique=True, nullable=False)
#     password = db.Column(db.String(128), nullable=False)
#     role = db.Column(db.String(16), nullable=False)
#     # Можно добавить связь с Student, если потребуется 