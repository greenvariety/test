from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from app.models import Faculty, Group, Student
from app import db
from sqlalchemy import func, or_
import functools # для functools.cmp_to_key если понадобится сложная сортировка

# Условный "текущий" год для всех расчетов курса и статуса в системе
EFFECTIVE_SYSTEM_YEAR = 2025
# Условный "текущий" месяц для определения начала учебного года (например, сентябрь)
# Если EFFECTIVE_SYSTEM_YEAR используется как уже НАЧАЛО учебного года, то месяц не так важен.
# Для простоты будем считать, что EFFECTIVE_SYSTEM_YEAR - это уже актуальный учебный год.

bp = Blueprint('groups', __name__, url_prefix='/groups') # Общий префикс для групп

# Маршрут для списка групп конкретного факультета
# Он будет доступен через /faculties/<faculty_id>/groups/
faculty_groups_bp = Blueprint('faculty_groups', __name__, url_prefix='/faculties/<int:faculty_id>/groups')

def get_sort_key(item, column):
    # Вспомогательная функция для получения ключа сортировки
    # Для числовых полей возвращаем число, для строковых - строку в нижнем регистре
    val = item.get(column)
    if isinstance(val, (int, float)):
        return val
    if isinstance(val, str):
        return val.lower()
    return val # На случай None или других типов

@faculty_groups_bp.route('/')
def list_groups(faculty_id):
    faculty = Faculty.query.get_or_404(faculty_id)
    
    search_query = request.args.get('search_query', '').strip()
    # Если sort_by не указан в запросе, он будет None.
    # Это позволит нам не отображать стрелку сортировки в шаблоне по умолчанию.
    sort_column_from_request = request.args.get('sort_by')
    current_sort_order = request.args.get('order', 'asc') # Порядок по умолчанию, если колонка задана

    groups_from_db = Group.query.filter_by(faculty_id=faculty.id).all()
    
    processed_groups = []
    for group_obj in groups_from_db:
        course = (EFFECTIVE_SYSTEM_YEAR - group_obj.year) + 1
        if course < 1: course = 1
        elif course > group_obj.duration: course = group_obj.duration
        
        status = "Учится"
        if (EFFECTIVE_SYSTEM_YEAR - group_obj.year + 1) > group_obj.duration: status = "Выпущена"
        
        num_students = Student.query.filter_by(group_id=group_obj.id).count() if hasattr(Student, 'group_id') else 0
        
        processed_groups.append({
            'id': group_obj.id,
            'name': group_obj.name,
            'year': group_obj.year,
            'duration': group_obj.duration,
            'course': course,
            'status': status,
            'num_students': num_students,
            'faculty_short_name': faculty.short_name # Это может не понадобиться в контексте этого списка
        })

    # Фильтрация (поиск)
    if search_query:
        filtered_groups = []
        sq_lower = search_query.lower()
        for group_dict in processed_groups:
            if (
                sq_lower in str(group_dict['name']).lower() or
                sq_lower in str(group_dict['year']).lower() or
                sq_lower in str(group_dict['duration']).lower() or
                sq_lower in str(group_dict['course']).lower() or
                sq_lower in str(group_dict['status']).lower() or
                sq_lower in str(group_dict['num_students']).lower()
            ):
                filtered_groups.append(group_dict)
        processed_groups = filtered_groups

    # Сортировка
    # Определяем колонку для фактической сортировки данных
    actual_sort_column = sort_column_from_request if sort_column_from_request else 'name' # Сортируем по имени по умолчанию
    
    if actual_sort_column != 'default' and processed_groups and actual_sort_column in processed_groups[0]:
        processed_groups.sort(key=lambda x: get_sort_key(x, actual_sort_column), reverse=(current_sort_order == 'desc'))
    elif not processed_groups:
        pass
    else: # Сортировка по умолчанию (если actual_sort_column == 'default' или его нет в ключах)
        processed_groups.sort(key=lambda x: x['name'].lower()) # по имени asc

    return render_template('groups/list.html', 
                           groups=processed_groups, 
                           faculty=faculty,
                           search_query=search_query,
                           # Передаем в шаблон исходное значение sort_by из запроса (может быть None)
                           sort_by=sort_column_from_request, 
                           order=current_sort_order)

@faculty_groups_bp.route('/create', methods=['GET', 'POST'])
def create_group(faculty_id):
    faculty = Faculty.query.get_or_404(faculty_id)
    
    if request.method == 'POST':
        try:
            year_str = request.form.get('year')
            duration_str = request.form.get('duration')

            if not year_str or not duration_str:
                flash('Год поступления и срок обучения являются обязательными полями.', 'danger')
                return render_template('groups/create_edit.html', 
                                       faculty=faculty, 
                                       form_action=url_for('.create_group', faculty_id=faculty.id), 
                                       form_title="Создание новой группы",
                                       submitted_form_data=request.form)

            year = int(year_str)
            duration = int(duration_str)

            if not (2018 <= year <= 2042):
                flash('Год поступления должен быть между 2018 и 2042.', 'danger')
                return render_template('groups/create_edit.html', faculty=faculty, form_action=url_for('.create_group', faculty_id=faculty.id), form_title="Создание новой группы", submitted_form_data=request.form)
            
            if not (2 <= duration <= 6):
                flash('Срок обучения должен быть от 2 до 6 лет.', 'danger')
                return render_template('groups/create_edit.html', faculty=faculty, form_action=url_for('.create_group', faculty_id=faculty.id), form_title="Создание новой группы", submitted_form_data=request.form)

            # Расчет курса и статуса для сохранения в БД
            calculated_course = (EFFECTIVE_SYSTEM_YEAR - year) + 1
            if calculated_course < 1:
                calculated_course = 1
            elif calculated_course > duration:
                calculated_course = duration
            
            calculated_status = "Учится"
            if (EFFECTIVE_SYSTEM_YEAR - year + 1) > duration:
                calculated_status = "Выпущена"

            # Генерация имени группы
            existing_groups_count = Group.query.filter_by(faculty_id=faculty.id, year=year).count()
            group_index = existing_groups_count + 1
            year_short = str(year)[-2:] # Получаем последние две цифры года
            group_name = f"{faculty.short_name}-{group_index}-{year_short}"
            check_existing = Group.query.filter_by(name=group_name, faculty_id=faculty.id).first()
            while check_existing:
                group_index += 1
                # Обновляем имя с новым индексом
                group_name = f"{faculty.short_name}-{group_index}-{year_short}"
                check_existing = Group.query.filter_by(name=group_name, faculty_id=faculty.id).first()

            new_group = Group(name=group_name, 
                              year=year, 
                              duration=duration, 
                              faculty_id=faculty.id,
                              course=calculated_course,  # Сохраняем рассчитанный курс
                              status=calculated_status)  # Сохраняем рассчитанный статус
            db.session.add(new_group)
            db.session.commit()
            flash(f'Группа "{new_group.name}" успешно создана!', 'success')
            return redirect(url_for('.list_groups', faculty_id=faculty.id))
        
        except ValueError:
            flash('Год поступления и срок обучения должны быть корректными числами.', 'danger')
            return render_template('groups/create_edit.html', faculty=faculty, form_action=url_for('.create_group', faculty_id=faculty.id), form_title="Создание новой группы", submitted_form_data=request.form)
        except Exception as e:
            db.session.rollback()
            flash(f'Произошла непредвиденная ошибка при создании группы: {str(e)}', 'danger')
            return render_template('groups/create_edit.html', faculty=faculty, form_action=url_for('.create_group', faculty_id=faculty.id), form_title="Создание новой группы", submitted_form_data=request.form)

    return render_template('groups/create_edit.html', 
                           faculty=faculty, 
                           form_action=url_for('.create_group', faculty_id=faculty.id), 
                           form_title="Создание новой группы")

@bp.route('/<int:id>/edit', methods=['GET', 'POST'])
def edit_group(id):
    group_to_edit = Group.query.get_or_404(id)
    faculty = Faculty.query.get_or_404(group_to_edit.faculty_id)
    if request.method == 'POST':
        try:
            original_year = group_to_edit.year # Сохраняем оригинальный год для возможной перегенерации имени

            year_str = request.form.get('year')
            duration_str = request.form.get('duration')
            if not year_str or not duration_str:
                flash('Год поступления и срок обучения являются обязательными полями.', 'danger')
                return render_template('groups/create_edit.html', group=group_to_edit, faculty=faculty, form_action=url_for('groups.edit_group', id=id), form_title=f"Редактирование группы {group_to_edit.name}", submitted_form_data=request.form)
            
            year = int(year_str)
            duration = int(duration_str)

            if not (2018 <= year <= 2042):
                flash('Год поступления должен быть между 2018 и 2042.', 'danger')
                return render_template('groups/create_edit.html', group=group_to_edit, faculty=faculty, form_action=url_for('groups.edit_group', id=id), form_title=f"Редактирование группы {group_to_edit.name}", submitted_form_data=request.form)
            if not (2 <= duration <= 6):
                flash('Срок обучения должен быть от 2 до 6 лет.', 'danger')
                return render_template('groups/create_edit.html', group=group_to_edit, faculty=faculty, form_action=url_for('groups.edit_group', id=id), form_title=f"Редактирование группы {group_to_edit.name}", submitted_form_data=request.form)

            # Логика перегенерации имени, если изменился год
            if original_year != year:
                # Нужно найти новый group_index для нового года, исключая текущую редактируемую группу из подсчета
                # Это важно, чтобы не было конфликта 'сам с собой' и чтобы номер был корректным
                existing_groups_count_for_new_year = Group.query.filter(
                    Group.faculty_id == faculty.id, 
                    Group.year == year,
                    Group.id != group_to_edit.id # Исключаем текущую группу
                ).count()
                new_group_index = existing_groups_count_for_new_year + 1
                year_short = str(year)[-2:] # Получаем последние две цифры года
                new_group_name = f"{faculty.short_name}-{new_group_index}-{year_short}"
                
                # Проверка на уникальность, на всякий случай, если вдруг такой номер уже занят другой группой (маловероятно при правильном подсчете)
                temp_check_existing = Group.query.filter_by(name=new_group_name, faculty_id=faculty.id).first()
                while temp_check_existing and temp_check_existing.id != group_to_edit.id:
                    new_group_index += 1
                    new_group_name = f"{faculty.short_name}-{new_group_index}-{year_short}"
                    temp_check_existing = Group.query.filter_by(name=new_group_name, faculty_id=faculty.id).first()
                group_to_edit.name = new_group_name
            
            group_to_edit.year = year
            group_to_edit.duration = duration
            
            # Пересчитываем курс и статус на основе новых данных и EFFECTIVE_SYSTEM_YEAR
            calculated_course = (EFFECTIVE_SYSTEM_YEAR - year) + 1
            if calculated_course < 1: calculated_course = 1
            elif calculated_course > duration: calculated_course = duration
            group_to_edit.course = calculated_course

            calculated_status = "Учится"
            if (EFFECTIVE_SYSTEM_YEAR - year + 1) > duration:
                calculated_status = "Выпущена"
            group_to_edit.status = calculated_status
            
            db.session.commit()
            flash(f'Группа "{group_to_edit.name}" успешно обновлена!', 'success')
            return redirect(url_for('faculty_groups.list_groups', faculty_id=faculty.id))

        except ValueError:
            flash('Год поступления и срок обучения должны быть корректными числами.', 'danger')
            return render_template('groups/create_edit.html', group=group_to_edit, faculty=faculty, form_action=url_for('groups.edit_group', id=id), form_title=f"Редактирование группы {group_to_edit.name}", submitted_form_data=request.form)
        except Exception as e:
            db.session.rollback()
            flash(f'Произошла непредвиденная ошибка при обновлении группы: {str(e)}', 'danger')
            return render_template('groups/create_edit.html', group=group_to_edit, faculty=faculty, form_action=url_for('groups.edit_group', id=id), form_title=f"Редактирование группы {group_to_edit.name}", submitted_form_data=request.form)

    return render_template('groups/create_edit.html', group=group_to_edit, faculty=faculty, form_action=url_for('groups.edit_group', id=group_to_edit.id), form_title=f"Редактирование группы {group_to_edit.name}")

@bp.route('/<int:id>/delete', methods=['POST'])
def delete_group(id):
    group_to_delete = Group.query.get_or_404(id)
    faculty_id_redirect = group_to_delete.faculty_id # Запоминаем для редиректа
    group_name = group_to_delete.name
    try:
        # Если есть студенты и модель Student имеет group_id, и настроено каскадное удаление в SQLAlchemy,
        # то студенты удалятся автоматически. 
        # Если нет, и мы хотим их удалить, нужно сделать это явно:
        # Student.query.filter_by(group_id=id).delete()
        # Сейчас, предполагая, что каскадное удаление настроено или студенты обрабатываются отдельно:
        db.session.delete(group_to_delete)
        db.session.commit()
        flash(f'Группа "{group_name}" и все связанные с ней студенты (если настроено каскадное удаление) были успешно удалены.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Ошибка при удалении группы "{group_name}": {str(e)}', 'danger')
    return redirect(url_for('faculty_groups.list_groups', faculty_id=faculty_id_redirect))

# Маршруты для CRUD групп будут добавлены сюда и в bp (для /groups/<id>/edit и /groups/<id>/delete) 