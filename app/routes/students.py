from flask import Blueprint, render_template, abort, request, redirect, url_for, flash
from app.models import Group, Student # Нам понадобятся модели Group и Student
from app import db # Если будем что-то менять в БД, но для списка пока не нужно
from sqlalchemy.exc import IntegrityError
from sqlalchemy import or_ # Для более сложных фильтров SQLAlchemy, если понадобится
from datetime import datetime # Для преобразования строки в дату
from werkzeug.utils import secure_filename
from flask import current_app
import os
import uuid

# Создаем два блюпринта:
# 1. group_students_bp: для действий, связанных со студентами В КОНТЕКСТЕ группы 
#    (например, список студентов группы, добавление студента в группу)
#    URL: /groups/<int:group_id>/students/...
# 2. students_bp: для общих действий со студентами, не привязанных к конкретной группе сразу
#    (например, редактирование студента по его ID, удаление студента по его ID)
#    URL: /students/...

group_students_bp = Blueprint('group_students', __name__, url_prefix='/groups/<int:group_id>/students')
students_bp = Blueprint('students', __name__, url_prefix='/students')

def get_student_sort_key(item, column):
    val = item.get(column) # item - это словарь
    if isinstance(val, (int, float)):
        return val
    if isinstance(val, datetime):
        return val # Даты можно сравнивать напрямую
    if isinstance(val, str):
        return val.lower()
    return str(val).lower() # Для None или других типов, приводим к строке

@group_students_bp.route('/')
def list_students_in_group(group_id):
    group = Group.query.get_or_404(group_id)
    
    search_query = request.args.get('search_query', '').strip()
    
    # Получаем sort_by из запроса. Если его нет, будет None.
    sort_column_for_template = request.args.get('sort_by')
    current_sort_order = request.args.get('order', 'asc')

    # Сначала получаем всех студентов группы из БД
    students_from_db = Student.query.filter_by(group_id=group.id).all()

    # Преобразуем в список словарей для удобства фильтрации и сортировки на Python
    # т.к. поиск по форматированной дате сложен в SQLAlchemy напрямую
    processed_students = []
    for student_obj in students_from_db:
        processed_students.append({
            'id': student_obj.id,
            'full_name': student_obj.full_name,
            'date_of_birth': student_obj.date_of_birth, # Оставляем как объект date для сортировки
            'date_of_birth_str': student_obj.date_of_birth.strftime('%d.%m.%Y') if student_obj.date_of_birth else '-', # Строка для отображения и поиска
            'phone_number': student_obj.phone_number,
            'email': student_obj.email,
            # Не передаем student_obj целиком, чтобы случайно не изменить его в шаблоне
        })

    # Фильтрация (поиск)
    if search_query:
        filtered_students = []
        sq_lower = search_query.lower()
        for student_dict in processed_students:
            if (
                sq_lower in str(student_dict['full_name']).lower() or
                sq_lower in student_dict['date_of_birth_str'].lower() or # Поиск по строке даты
                (student_dict['phone_number'] and sq_lower in str(student_dict['phone_number']).lower()) or
                (student_dict['email'] and sq_lower in str(student_dict['email']).lower())
            ):
                filtered_students.append(student_dict)
        processed_students = filtered_students

    # Сортировка
    # Определяем колонку для ФАКТИЧЕСКОЙ сортировки данных
    actual_sort_column_for_data = sort_column_for_template if sort_column_for_template else 'full_name'
    valid_sort_columns = ['full_name', 'date_of_birth', 'phone_number', 'email']

    if processed_students: # Только если есть что сортировать
        if actual_sort_column_for_data != 'default' and actual_sort_column_for_data in valid_sort_columns:
            processed_students.sort(key=lambda x: get_student_sort_key(x, actual_sort_column_for_data), reverse=(current_sort_order == 'desc'))
        else: # Сортировка по умолчанию (full_name asc)
            processed_students.sort(key=lambda x: get_student_sort_key(x, 'full_name')) # Явно указываем full_name

    return render_template('students/list.html', 
                           students=processed_students, 
                           group=group,
                           faculty=group.faculty, # Передаем факультет для хлебных крошек
                           search_query=search_query,
                           sort_by=sort_column_for_template, # Передаем None или значение из URL
                           order=current_sort_order)

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in current_app.config['ALLOWED_EXTENSIONS']

# TODO: Добавить другие маршруты для CRUD студентов:
@group_students_bp.route('/create', methods=['GET', 'POST'])
def create_student_in_group(group_id):
    group = Group.query.get_or_404(group_id)
    if request.method == 'POST':
        full_name = request.form.get('full_name')
        date_of_birth_str = request.form.get('date_of_birth')
        phone_number = request.form.get('phone_number')
        email = request.form.get('email')
        photo = request.files.get('photo')
        photo_filename_to_save = None

        if not all([full_name, date_of_birth_str, phone_number, email]):
            flash('Все поля, кроме фото, обязательны для заполнения.', 'danger')
            # Передаем введенные данные обратно в шаблон
            return render_template('students/create_edit.html', group=group, form_action=url_for('.create_student_in_group', group_id=group_id), form_title="Добавление нового студента", submitted_form_data=request.form)
        
        try:
            date_of_birth = datetime.strptime(date_of_birth_str, '%Y-%m-%d').date()
        except ValueError:
            flash('Неверный формат даты рождения. Используйте ГГГГ-ММ-ДД.', 'danger')
            return render_template('students/create_edit.html', group=group, form_action=url_for('.create_student_in_group', group_id=group_id), form_title="Добавление нового студента", submitted_form_data=request.form)

        if photo:
            if allowed_file(photo.filename):
                filename = secure_filename(photo.filename)
                # Для уникальности можно добавить timestamp или uuid к имени файла
                # Например: filename = str(uuid.uuid4()) + "_" + secure_filename(photo.filename)
                photo.save(os.path.join(current_app.config['UPLOAD_FOLDER'], filename))
                photo_filename_to_save = filename
            else:
                flash('Недопустимый тип файла для фотографии. Разрешены PNG, JPG, JPEG.', 'danger')
                return render_template('students/create_edit.html', group=group, form_action=url_for('.create_student_in_group', group_id=group_id), form_title="Добавление нового студента", submitted_form_data=request.form)

        try:
            new_student = Student(
                full_name=full_name, 
                date_of_birth=date_of_birth, 
                phone_number=phone_number, 
                email=email, 
                group_id=group.id,
                photo_filename=photo_filename_to_save
            )
            db.session.add(new_student)
            db.session.commit()
            flash(f'Студент "{new_student.full_name}" успешно добавлен в группу {group.name}!', 'success')
            return redirect(url_for('.list_students_in_group', group_id=group.id))
        except IntegrityError: # Обработка ошибки уникальности email
            db.session.rollback()
            flash('Студент с таким email уже существует.', 'danger')
        except Exception as e:
            db.session.rollback()
            flash(f'Произошла ошибка при добавлении студента: {str(e)}', 'danger')
            
    return render_template('students/create_edit.html', group=group, form_action=url_for('.create_student_in_group', group_id=group_id), form_title="Добавление нового студента")

@students_bp.route('/<int:student_id>/edit', methods=['GET', 'POST'])
def edit_student(student_id):
    student_to_edit = Student.query.get_or_404(student_id)
    group = student_to_edit.group # Получаем группу студента для хлебных крошек и т.д.

    if request.method == 'POST':
        full_name = request.form.get('full_name')
        date_of_birth_str = request.form.get('date_of_birth')
        phone_number = request.form.get('phone_number')
        email = request.form.get('email')
        photo = request.files.get('photo')
        delete_photo_checkbox = request.form.get('delete_photo')

        if not all([full_name, date_of_birth_str, phone_number, email]):
            flash('Все поля, кроме фото, обязательны для заполнения.', 'danger')
            return render_template('students/create_edit.html', student=student_to_edit, group=group, form_action=url_for('.edit_student', student_id=student_id), form_title=f"Редактирование студента: {student_to_edit.full_name}", submitted_form_data=request.form)

        try:
            date_of_birth = datetime.strptime(date_of_birth_str, '%Y-%m-%d').date()
        except ValueError:
            flash('Неверный формат даты рождения. Используйте ГГГГ-ММ-ДД.', 'danger')
            return render_template('students/create_edit.html', student=student_to_edit, group=group, form_action=url_for('.edit_student', student_id=student_id), form_title=f"Редактирование студента: {student_to_edit.full_name}", submitted_form_data=request.form)

        # Логика обработки фотографии
        if delete_photo_checkbox and student_to_edit.photo_filename:
            # Удаляем старый файл
            try:
                os.remove(os.path.join(current_app.config['UPLOAD_FOLDER'], student_to_edit.photo_filename))
            except OSError:
                flash('Ошибка при удалении старой фотографии. Файл не найден.', 'warning')
            student_to_edit.photo_filename = None
        
        if photo: # Если загружен новый файл
            if allowed_file(photo.filename):
                # Удаляем старый файл, если он был и не был помечен на удаление выше (на случай если грузят новый не удаляя старый явно)
                if student_to_edit.photo_filename and not delete_photo_checkbox:
                    try:
                        os.remove(os.path.join(current_app.config['UPLOAD_FOLDER'], student_to_edit.photo_filename))
                    except OSError:
                        pass # Молча пропускаем, если старый файл не найден
                
                filename = secure_filename(photo.filename)
                # filename = str(uuid.uuid4()) + "_" + secure_filename(photo.filename) # Для уникальности
                photo.save(os.path.join(current_app.config['UPLOAD_FOLDER'], filename))
                student_to_edit.photo_filename = filename
            else:
                flash('Недопустимый тип файла для фотографии. Разрешены PNG, JPG, JPEG.', 'danger')
                return render_template('students/create_edit.html', student=student_to_edit, group=group, form_action=url_for('.edit_student', student_id=student_id), form_title=f"Редактирование студента: {student_to_edit.full_name}", submitted_form_data=request.form)

        student_to_edit.full_name = full_name
        student_to_edit.date_of_birth = date_of_birth
        student_to_edit.phone_number = phone_number
        student_to_edit.email = email
        
        try:
            db.session.commit()
            flash(f'Данные студента "{student_to_edit.full_name}" успешно обновлены!', 'success')
            return redirect(url_for('group_students.list_students_in_group', group_id=group.id)) # Редирект на список студентов группы
        except IntegrityError: # Обработка ошибки уникальности email
            db.session.rollback()
            flash('Студент с таким email уже существует (и это не данный студент).', 'danger')
        except Exception as e:
            db.session.rollback()
            flash(f'Произошла ошибка при обновлении данных студента: {str(e)}', 'danger')

    return render_template('students/create_edit.html', student=student_to_edit, group=group, form_action=url_for('.edit_student', student_id=student_id), form_title=f"Редактирование студента: {student_to_edit.full_name}")

@students_bp.route('/<int:student_id>/view_card')
def view_student_card(student_id):
    student = Student.query.get_or_404(student_id)
    return render_template('students/view_card.html', student=student)

@students_bp.route('/<int:student_id>/delete', methods=['POST'])
def delete_student(student_id):
    student_to_delete = Student.query.get_or_404(student_id)
    group_id_redirect = student_to_delete.group_id
    student_full_name = student_to_delete.full_name
    photo_to_delete = student_to_delete.photo_filename # Сохраняем имя файла перед удалением объекта

    try:
        db.session.delete(student_to_delete)
        db.session.commit()

        # Удаляем файл фотографии, если он был
        if photo_to_delete:
            try:
                os.remove(os.path.join(current_app.config['UPLOAD_FOLDER'], photo_to_delete))
            except OSError:
                flash(f'Фотография для студента {student_full_name} не найдена на диске, но запись из БД удалена.', 'warning')

        flash(f'Студент "{student_full_name}" успешно удален.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Ошибка при удалении студента: {str(e)}', 'danger')
    
    return redirect(url_for('group_students.list_students_in_group', group_id=group_id_redirect))

# Дальнейшие TODO для поиска/сортировки и т.д. в list_students_in_group

# @students_bp.route('/<int:student_id>/delete', methods=['POST'])
# def delete_student(student_id):
#     pass 