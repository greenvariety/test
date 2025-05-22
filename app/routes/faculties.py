from flask import Blueprint, render_template, request, redirect, url_for, flash
from app import db
from app.models import Faculty, Group, Student
from sqlalchemy import func, or_
import re

bp = Blueprint('faculties', __name__, url_prefix='/faculties')

def get_sort_key_faculties(item, column):
    val = item.get(column)
    if isinstance(val, (int, float)):
        return val
    if isinstance(val, str):
        return val.lower()
    return val

@bp.route('/')
def list_faculties():
    search_query = request.args.get('search_query', '').strip()
    sort_column = request.args.get('sort_by', 'default')
    sort_order = request.args.get('order', 'asc')

    query = Faculty.query
    if search_query:
        search_term = f"%{search_query.lower()}%".lower()
        query = query.filter(
            or_(
                func.lower(Faculty.name).like(search_term),
                func.lower(Faculty.short_name).like(search_term),
                func.lower(Faculty.description).like(search_term)
            )
        )
    
    faculties_list_from_db = query.all()
    faculties_processed = []
    for faculty_obj in faculties_list_from_db:
        num_groups = Group.query.with_parent(faculty_obj).count()
        num_students = Student.query.join(Group).filter(Group.faculty_id == faculty_obj.id).count() if hasattr(Student, 'group_id') else 0
        faculties_processed.append({
            'id': faculty_obj.id,
            'name': faculty_obj.name,
            'short_name': faculty_obj.short_name,
            'description': faculty_obj.description,
            'num_groups': num_groups,
            'num_students': num_students
        })

    if sort_column != 'default' and sort_column in faculties_processed[0].keys() if faculties_processed else False:
        faculties_processed.sort(key=lambda x: get_sort_key_faculties(x, sort_column), reverse=(sort_order == 'desc'))
    elif not faculties_processed:
        pass
    else:
         faculties_processed.sort(key=lambda x: x['id'])

    return render_template('faculties/list.html', 
                           faculties=faculties_processed,
                           search_query=search_query,
                           sort_by=sort_column,
                           order=sort_order
                           )

@bp.route('/create', methods=['GET', 'POST'])
def create_faculty():
    if request.method == 'POST':
        name = request.form.get('name')
        short_name = request.form.get('short_name')
        description = request.form.get('description')
        if name and short_name:
            existing_faculty = Faculty.query.filter(
                or_(Faculty.name == name, Faculty.short_name == short_name)
            ).first()
            if existing_faculty:
                flash('Факультет с таким названием или сокращением уже существует.', 'danger')
            else:
                new_faculty = Faculty(name=name, short_name=short_name, description=description)
                db.session.add(new_faculty)
                db.session.commit()
                flash(f'Факультет "{new_faculty.name}" успешно создан!', 'success')
                return redirect(url_for('.list_faculties'))
        else:
            flash('Название и сокращение являются обязательными полями.', 'danger')
    return render_template('faculties/create_edit.html', form_title="Создание нового факультета", form_action=url_for('.create_faculty'))

@bp.route('/<int:id>/edit', methods=['GET', 'POST'])
def edit_faculty(id):
    faculty_to_edit = Faculty.query.get_or_404(id)
    original_short_name = faculty_to_edit.short_name

    if request.method == 'POST':
        new_name = request.form.get('name')
        new_short_name = request.form.get('short_name')
        new_description = request.form.get('description')

        if new_name and new_short_name:
            existing_faculty_conflict = Faculty.query.filter(
                or_(Faculty.name == new_name, Faculty.short_name == new_short_name),
                Faculty.id != id
            ).first()

            if existing_faculty_conflict:
                flash('Другой факультет с таким названием или сокращением уже существует.', 'danger')
            else:
                faculty_to_edit.name = new_name
                faculty_to_edit.short_name = new_short_name
                faculty_to_edit.description = new_description
                
                db.session.add(faculty_to_edit)

                if original_short_name != new_short_name:
                    related_groups = Group.query.filter_by(faculty_id=id).all()
                    for group in related_groups:
                        try:
                            parts = group.name.split('-')
                            if len(parts) == 3:
                                number_str = parts[1]
                                year_short_str = parts[2]
                                new_group_name = f"{new_short_name}-{number_str}-{year_short_str}"
                                
                                check_existing = Group.query.filter_by(name=new_group_name, faculty_id=id).first()
                                if check_existing and check_existing.id != group.id:
                                    flash(f'Не удалось автоматически обновить имя группы {group.name} из-за конфликта. Обновите вручную.', 'warning')
                                    continue

                                group.name = new_group_name
                                db.session.add(group)
                            else:
                                flash(f'Не удалось автоматически разобрать имя группы {group.name} для обновления.', 'warning')
                        except Exception as e_group_rename:
                            flash(f'Ошибка при попытке автоматического обновления имени группы {group.name}: {str(e_group_rename)}', 'warning')
                
                try:
                    db.session.commit()
                    flash(f'Факультет "{faculty_to_edit.name}" успешно обновлен!', 'success')
                    if original_short_name != new_short_name:
                         flash(f'Имена связанных групп были также обновлены с новым сокращением "{new_short_name}".', 'info')
                    return redirect(url_for('.list_faculties'))
                except Exception as e_commit:
                    db.session.rollback()
                    flash(f'Ошибка при сохранении изменений: {str(e_commit)}', 'danger')
        else:
            flash('Название и сокращение являются обязательными полями.', 'danger')
        
    return render_template('faculties/create_edit.html', 
                           faculty=faculty_to_edit, 
                           form_title=f"Редактировать: {faculty_to_edit.name}", 
                           form_action=url_for('.edit_faculty', id=id))

@bp.route('/<int:id>/delete', methods=['POST'])
def delete_faculty(id):
    faculty_to_delete = Faculty.query.get_or_404(id)
    if faculty_to_delete.groups:
        flash(f'Факультет "{faculty_to_delete.name}" не может быть удален, так как за ним закреплены группы.', 'danger')
        return redirect(url_for('.list_faculties'))
    try:
        db.session.delete(faculty_to_delete)
        db.session.commit()
        flash(f'Факультет "{faculty_to_delete.name}" успешно удален!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Ошибка при удалении факультета: {str(e)}', 'danger')
    return redirect(url_for('.list_faculties'))
