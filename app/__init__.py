from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
# from flask_login import LoginManager # Убираем Flask-Login
import datetime

# Инициализация расширений

db = SQLAlchemy()
migrate = Migrate()
# login_manager = LoginManager() # Убираем Flask-Login


def create_app():
    app = Flask(__name__)
    app.config['SECRET_KEY'] = 'your_secret_key_here'
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///db.sqlite3'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    db.init_app(app)
    migrate.init_app(app, db)
    # login_manager.init_app(app) # Убираем Flask-Login

    from . import models  # Импорт моделей после инициализации расширений
    # from .auth import bp as auth_bp # Убираем импорт auth blueprint
    # app.register_blueprint(auth_bp) # Убираем регистрацию auth blueprint

    from .routes.faculties import bp as faculties_bp # Импорт blueprint факультетов
    app.register_blueprint(faculties_bp) # Регистрация blueprint факультетов

    from .routes.groups import faculty_groups_bp # Импорт blueprint для групп факультета
    app.register_blueprint(faculty_groups_bp)   # Регистрация blueprint
    from .routes.groups import bp as groups_bp # Общий blueprint для групп (для edit/delete)
    app.register_blueprint(groups_bp)

    from .routes.students import group_students_bp # Импорт blueprint для студентов группы
    app.register_blueprint(group_students_bp)   # Регистрация blueprint
    from .routes.students import students_bp # Общий blueprint для студентов (для edit/delete)
    app.register_blueprint(students_bp)

    @app.route('/')
    def index():
        return 'Приложение для учета студентов, групп и факультетов' # Простое приветствие

    @app.context_processor
    def inject_current_year():
        return {'current_year': datetime.datetime.utcnow().year}

    # Импорт и регистрация других blueprint'ов будет позже

    return app 