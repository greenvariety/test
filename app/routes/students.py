from flask import Blueprint, render_template, abort, request, redirect, url_for, flash
from app.models import Group, Student # Нам понадобятся модели Group и Student
from app import db # Если будем что-то менять в БД, но для списка пока не нужно
from sqlalchemy.exc import IntegrityError
from sqlalchemy import or_ # Для более сложных фильтров SQLAlchemy, если понадобится
from datetime import datetime # Для преобразования строки в дату

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

# TODO: Добавить другие маршруты для CRUD студентов:
@group_students_bp.route('/create', methods=['GET', 'POST'])
def create_student_in_group(group_id):
    group = Group.query.get_or_404(group_id)
    if request.method == 'POST':
        try:
            full_name = request.form.get('full_name')
            date_of_birth_str = request.form.get('date_of_birth')
            phone_number = request.form.get('phone_number')
            email = request.form.get('email')

            # Проверка на обязательные поля (хотя HTML5 required должен это покрывать)
            if not all([full_name, date_of_birth_str, phone_number, email]):
                flash('Все поля обязательны для заполнения.', 'danger')
                return render_template('students/create_edit.html', 
                                       group=group,
                                       form_title=f"Добавление студента в группу {group.name}",
                                       form_action=url_for('.create_student_in_group', group_id=group.id),
                                       student=None, # Для совместимости с редактированием
                                       submitted_form_data=request.form) # Чтобы вернуть введенные данные

            try:
                date_of_birth_obj = datetime.strptime(date_of_birth_str, '%Y-%m-%d').date()
            except ValueError:
                flash('Неверный формат даты рождения. Используйте ГГГГ-ММ-ДД.', 'danger')
                return render_template('students/create_edit.html', 
                                       group=group,
                                       form_title=f"Добавление студента в группу {group.name}",
                                       form_action=url_for('.create_student_in_group', group_id=group.id),
                                       student=None, 
                                       submitted_form_data=request.form)

            new_student = Student(
                full_name=full_name,
                date_of_birth=date_of_birth_obj,
                phone_number=phone_number,
                email=email,
                group_id=group.id
            )
            db.session.add(new_student)
            db.session.commit()
            flash(f'Студент "{new_student.full_name}" успешно добавлен в группу {group.name}!', 'success')
            return redirect(url_for('.list_students_in_group', group_id=group.id))
        
        except IntegrityError as e:
            db.session.rollback() # Откатываем сессию
            if 'UNIQUE constraint failed: student.email' in str(e):
                flash('Студент с таким email уже существует.', 'danger')
            else:
                flash(f'Ошибка базы данных: {str(e)}', 'danger')
            return render_template('students/create_edit.html', 
                                   group=group,
                                   form_title=f"Добавление студента в группу {group.name}",
                                   form_action=url_for('.create_student_in_group', group_id=group.id),
                                   student=None, 
                                   submitted_form_data=request.form)
        except Exception as e:
            db.session.rollback()
            flash(f'Произошла непредвиденная ошибка: {str(e)}', 'danger')
            return render_template('students/create_edit.html', 
                                   group=group,
                                   form_title=f"Добавление студента в группу {group.name}",
                                   form_action=url_for('.create_student_in_group', group_id=group.id),
                                   student=None, 
                                   submitted_form_data=request.form)

    # Для GET запроса просто отображаем форму
    return render_template('students/create_edit.html', 
                           group=group,
                           form_title=f"Добавление студента в группу {group.name}",
                           form_action=url_for('.create_student_in_group', group_id=group.id)
                           # student=None (для совместимости с редактированием)
                          )

@students_bp.route('/<int:student_id>/edit', methods=['GET', 'POST'])
def edit_student(student_id):
    student_to_edit = Student.query.get_or_404(student_id)
    group = Group.query.get_or_404(student_to_edit.group_id) # Нужна группа для хлебных крошек и редиректа

    if request.method == 'POST':
        try:
            full_name = request.form.get('full_name')
            date_of_birth_str = request.form.get('date_of_birth')
            phone_number = request.form.get('phone_number')
            email = request.form.get('email')

            if not all([full_name, date_of_birth_str, phone_number, email]):
                flash('Все поля обязательны для заполнения.', 'danger')
                # При ошибке снова рендерим шаблон с уже введенными данными
                return render_template('students/create_edit.html', 
                                       group=group,
                                       student=student_to_edit, # Передаем редактируемого студента
                                       form_title=f"Редактирование студента {student_to_edit.full_name}",
                                       form_action=url_for('students.edit_student', student_id=student_to_edit.id),
                                       submitted_form_data=request.form)
            
            try:
                date_of_birth_obj = datetime.strptime(date_of_birth_str, '%Y-%m-%d').date()
            except ValueError:
                flash('Неверный формат даты рождения. Используйте ГГГГ-ММ-ДД.', 'danger')
                return render_template('students/create_edit.html', 
                                       group=group, 
                                       student=student_to_edit,
                                       form_title=f"Редактирование студента {student_to_edit.full_name}",
                                       form_action=url_for('students.edit_student', student_id=student_to_edit.id),
                                       submitted_form_data=request.form)

            student_to_edit.full_name = full_name
            student_to_edit.date_of_birth = date_of_birth_obj
            student_to_edit.phone_number = phone_number
            student_to_edit.email = email
            # student_to_edit.group_id не меняем здесь, для смены группы нужен отдельный механизм
            
            db.session.commit()
            flash(f'Данные студента "{student_to_edit.full_name}" успешно обновлены!', 'success')
            return redirect(url_for('group_students.list_students_in_group', group_id=group.id))

        except IntegrityError as e:
            db.session.rollback()
            if 'UNIQUE constraint failed: student.email' in str(e):
                flash('Студент с таким email уже существует.', 'danger')
            else:
                flash(f'Ошибка базы данных при обновлении: {str(e)}', 'danger')
            return render_template('students/create_edit.html', 
                                   group=group, 
                                   student=student_to_edit,
                                   form_title=f"Редактирование студента {student_to_edit.full_name}",
                                   form_action=url_for('students.edit_student', student_id=student_to_edit.id),
                                   submitted_form_data=request.form)
        except Exception as e:
            db.session.rollback()
            flash(f'Произошла непредвиденная ошибка при обновлении: {str(e)}', 'danger')
            return render_template('students/create_edit.html', 
                                   group=group, 
                                   student=student_to_edit,
                                   form_title=f"Редактирование студента {student_to_edit.full_name}",
                                   form_action=url_for('students.edit_student', student_id=student_to_edit.id),
                                   submitted_form_data=request.form)

    # Для GET запроса
    return render_template('students/create_edit.html', 
                           group=group, 
                           student=student_to_edit, 
                           form_title=f"Редактирование студента {student_to_edit.full_name}",
                           form_action=url_for('students.edit_student', student_id=student_to_edit.id)
                          )

@students_bp.route('/<int:student_id>/delete', methods=['POST'])
def delete_student(student_id):
    student_to_delete = Student.query.get_or_404(student_id)
    group_id_redirect = student_to_delete.group_id # Запоминаем для редиректа
    student_name = student_to_delete.full_name
    try:
        db.session.delete(student_to_delete)
        db.session.commit()
        flash(f'Студент "{student_name}" был успешно удален.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Произошла ошибка при удалении студента "{student_name}": {str(e)}', 'danger')
    
    return redirect(url_for('group_students.list_students_in_group', group_id=group_id_redirect))

# Дальнейшие TODO для поиска/сортировки и т.д. в list_students_in_group

# @students_bp.route('/<int:student_id>/delete', methods=['POST'])
# def delete_student(student_id):
#     pass 