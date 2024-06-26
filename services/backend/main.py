from datetime import datetime, timedelta
from flask_restx import Api, Resource, Namespace, fields
from flask import request, jsonify, Flask
from app2.config import DevelopmentConfig

from flask.cli import FlaskGroup
from flask_cors import CORS


from extensions import db
from models import CREDENCIAL,Course,Enrollment

import bcrypt
import jwt
import os
import time

app = Flask(__name__)
app.config.from_object(DevelopmentConfig)

# Inicializa la extensión de base de datos
db.init_app(app)

# Configuración de CORS
CORS(app, resources={r"/api/*": {
    "origins": ["http://localhost:3000"],
    "methods": ["GET", "POST", "PATCH", "DELETE"],
    "allow_headers": ["Authorization", "Content-Type"],
    "supports_credentials": True,
    "max_age": 3600
}})


# Configuración de la API
api = Api(app, version="1.0", title="APIs", doc="/docs/")

# Namespace para operaciones relacionadas con alumnos
student_ns = Namespace('students', description='Operaciones relacionadas con alumnos')

# Modelo para creación y actualización de alumnos
student_model = student_ns.model('Student', {
    'rut': fields.String(required=True, description='RUT del estudiante'),  # Cambiado a rut
    'first_name': fields.String(required=True, description='Nombre del estudiante'),
    'last_name': fields.String(required=True, description='Apellido del estudiante'),
    'email': fields.String(required=True, description='Correo electrónico del estudiante'),
    'password': fields.String(required=True, description='Contraseña del estudiante'),
    'tipo_acceso': fields.String(required=True, description='Tipo de acceso (admin, profesor, alumno)'),
})

# Generación y verificación de tokens JWT
def generate_token(user_id):
    payload = {
        'exp': datetime.utcnow() + timedelta(days=1),
        'iat': datetime.utcnow(),
        'sub': user_id
    }
    return jwt.encode(payload, app.config['SECRET_KEY'], algorithm='HS256')

def token_required(f):
    def decorator(*args, **kwargs):
        token = None
        if 'Authorization' in request.headers:
            token = request.headers['Authorization'].split(" ")[1]
        if not token:
            return jsonify({"message": "Token is missing"}), 403
        try:
            data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
            current_user = CREDENCIAL.query.get(data['sub'])
        except:
            return jsonify({"message": "Token is invalid"}), 403
        return f(current_user, *args, **kwargs)
    decorator.__name__ = f.__name__
    return decorator







#################################################################### RUTAS USUARIO ####################################################################################
# para login de un alumno
@student_ns.route('/login')
class LoginStudent(Resource):
    def post(self):
        data = request.get_json()
        email = data.get('email')
        password = data.get('password')

        if not email or not password:
            return {"error": "Email and password are required"}, 400

        student = CREDENCIAL.query.filter_by(email=email).first()

        if not student or not bcrypt.checkpw(password.encode('utf-8'), student.password.encode('utf-8')):
            return {"error": "Invalid credentials"}, 401

        token = generate_token(student.id)
        return {"token": token, "message": "Login successful"}, 200

# para reestablecer clave, primero valida
@app.route('/api/validate-user', methods=['POST'])
def validate_user():
    data = request.get_json()
    name = data.get('name')
    rut = data.get('rut')

    user = CREDENCIAL.query.filter_by(first_name=name, rut=rut).first()
    if user:
        return jsonify({"message": "User validated successfully", "user_id": user.id}), 200
    else:
        return jsonify({"error": "Invalid name or RUT"}), 400
    
# para reestablecer clave, luego permite cambiar clave
@app.route('/api/reset-password', methods=['POST'])
def reset_password():
    data = request.get_json()
    user_id = data.get('user_id')
    new_password = data.get('newPassword')

    user = CREDENCIAL.query.get(user_id)
    if user:
        hashed_password = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        user.password = hashed_password
        db.session.commit()
        return jsonify({"message": "Password reset successful"}), 200
    else:
        return jsonify({"error": "User not found"}), 400

# Endpoint para crear un nuevo alumno
@student_ns.route('/creacion-nuevo-alumno')
class CreateStudent(Resource):
    @student_ns.expect(student_model)
    def post(self):
        data = request.get_json()
        email = data.get('email')
        password = data.get('password')
        rut = data.get('rut')

        if not email or not password or not rut:
            return {"error": "Email, password, and RUT are required"}, 400

        if CREDENCIAL.query.filter_by(email=email).first():
            return {"error": "User already exists"}, 409

        if CREDENCIAL.query.filter_by(rut=rut).first():
            return {"error": "RUT already exists"}, 409

        if not self.validate_rut_format(rut):
            return {"error": "Invalid RUT format"}, 400

        hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        new_student = CREDENCIAL(
            rut=rut,
            first_name=data.get('first_name'),
            last_name=data.get('last_name'),
            email=email,
            password=hashed_password,
            tipo_acceso=data.get('tipo_acceso')
        )
        db.session.add(new_student)
        db.session.commit()

        return {"message": "User registered successfully"}, 201

    def validate_rut_format(self, rut):
        import re
        return bool(re.match(r"^\d{1,3}(?:\.\d{3})*-[\dkK]$", rut))



# Resource para editar un alumno
@student_ns.route('/editar-alumno/<int:user_id>')
class EditStudent(Resource):
    @student_ns.expect(student_model)
    def patch(self, user_id):
        student = CREDENCIAL.query.get(user_id)
        if not student:
            return {"message": "User not found"}, 400
        
        data = request.json
        student.rut = data.get("rut", student.rut)
        student.first_name = data.get("first_name", student.first_name)
        student.last_name = data.get("last_name", student.last_name)
        student.email = data.get("email", student.email)
        student.password = data.get("password", student.password)
        student.tipo_acceso = data.get("tipo_acceso", student.tipo_acceso)

        db.session.commit()
        return {"message": "User updated successfully"}, 200

# Resource para eliminar un alumno
@student_ns.route('/eliminar-alumno/<int:user_id>')
class DeleteStudent(Resource):
    def delete(self, user_id):
        student = CREDENCIAL.query.get(user_id)
        if not student:
            return {"message": "User not found"}, 400
        
        db.session.delete(student)
        db.session.commit()
        return {"message": "User deleted successfully"}, 200

# Resource para buscar un alumno
@student_ns.route('/buscar-alumno/<int:user_id>')
class SearchStudent(Resource):
    def get(self, user_id):
        student = CREDENCIAL.query.get(user_id)
        if not student:
            return {"message": "User not found"}, 400
        
        return {
            "rut": student.rut,
            "first_name": student.first_name,
            "last_name": student.last_name,
            "email": student.email,
            "tipo_acceso": student.tipo_acceso
        }, 200
    
#################################################################### FIN RUTAS USUARIO ####################################################################################









#################################################################### RUTAS CURSOS ####################################################################################
# Endpoint to add a new course (admin only)
@student_ns.route('/add-course')
class AddCourse(Resource):
    @token_required
    def post(self, current_user):
        if current_user.tipo_acceso != 'admin':
            return {"error": "Admin access required"}, 403

        data = request.get_json()
        name = data.get('name')
        description = data.get('description')

        if not name:
            return {"error": "Course name is required"}, 400

        if Course.query.filter_by(name=name).first():
            return {"error": "Course already exists"}, 409

        new_course = Course(name=name, description=description)
        db.session.add(new_course)
        db.session.commit()

        return {"message": "Course added successfully"}, 201
    

# Endpoint to enroll a student or professor in a course
@student_ns.route('/enroll')
class EnrollCourse(Resource):
    @token_required
    def post(self, current_user):
        if current_user.tipo_acceso != 'admin':
            return {"error": "Admin access required"}, 403

        data = request.get_json()
        rut = data.get('rut')
        course_id = data.get('course_id')

        if not rut or not course_id:
            return {"error": "RUT and Course ID are required"}, 400

        user = CREDENCIAL.query.filter_by(rut=rut).first()
        if not user or user.tipo_acceso == 'admin':
            return {"error": "User not found or invalid user type"}, 404

        course = Course.query.get(course_id)
        if not course:
            return {"error": "Course not found"}, 404

        enrollment = Enrollment(rut=rut, course_id=course_id)
        db.session.add(enrollment)
        db.session.commit()

        return {"message": "Enrolled in course successfully"}, 201


# API Endpoint to get courses for a student
@student_ns.route('/courses')
class StudentCourses(Resource):
    @token_required
    def get(self, current_user):
        try:
            courses = db.session.query(Course).join(Enrollment).filter(Enrollment.rut == current_user.rut).all()
            return [course.to_dict() for course in courses], 200
        except AttributeError as e:
            return jsonify({"message": "Attribute error", "error": str(e)}), 400

# Agregar el namespace a la API
api.add_namespace(student_ns, path='/api')

#################################################################### FIN RUTAS CURSOS ####################################################################################







#################################################################### RUTAS ASISTENCIA ####################################################################################

# Namespace for Attendance
attendance_ns = Namespace('attendance', description='Attendance operations')

# Model for marking attendance
attendance_model = attendance_ns.model('Attendance', {
    'rut': fields.String(required=True, description='RUT of the student'),
    'course_id': fields.Integer(required=True, description='Course ID'),
    'date': fields.Date(required=True, description='Date of attendance'),
    'present': fields.Boolean(required=True, description='Presence status')
})


# Mark attendance
@attendance_ns.route('/mark')
class MarkAttendance(Resource):
    @attendance_ns.expect(attendance_model)
    def post(self):
        data = request.get_json()
        rut = data['rut']
        course_id = data['course_id']
        attendance_date = data['date']
        present = data['present']

        # Verificar el horario
        now = datetime.utcnow()
        if now.hour < 10 or now.hour >= 12:
            return {"error": "You can only mark attendance between 10:00 and 12:00 UTC."}, 400

        # Check if the student is enrolled in the course
        enrollment = Enrollment.query.filter_by(rut=rut, course_id=course_id).first()
        if not enrollment:
            return {"error": "Student not enrolled in the course"}, 400

        # Check if attendance for this date already exists
        existing_attendance = Attendance.query.filter_by(rut=rut, course_id=course_id, date=attendance_date).first()
        if existing_attendance:
            return {"error": "Attendance already marked for this date"}, 409

        # Add attendance record
        attendance = Attendance(rut=rut, course_id=course_id, date=attendance_date, present=present)
        db.session.add(attendance)
        db.session.commit()

        return {"message": "Attendance marked successfully"}, 201

# Get attendance records
@attendance_ns.route('/records')
class GetAttendanceRecords(Resource):
    def get(self):
        rut = request.args.get('rut')
        course_id = request.args.get('course_id')
        records = Attendance.query.filter_by(rut=rut, course_id=course_id).all()
        return jsonify([record.to_dict() for record in records])

# Get attendance count
@attendance_ns.route('/count')
class GetAttendanceCount(Resource):
    def get(self):
        rut = request.args.get('rut')
        course_id = request.args.get('course_id')
        count = Attendance.query.filter_by(rut=rut, course_id=course_id, present=True).count()
        return jsonify({'count': count})

# Add the namespace to the API
api.add_namespace(attendance_ns, path='/api')

#################################################################### RUTAS ASISTENCIA ####################################################################################




# Creación de usuarios para testing
def initialize_default_users():
    if not CREDENCIAL.query.first():
        users = [
            {
                'rut': '20.723.182-7',
                'first_name': 'Javiera',
                'last_name': 'Soto',
                'email': 'javi@correo.cl',
                'password': 'queso',
                'tipo_acceso': 'alumno'
            },
            {
                'rut': '19.654.321-0',
                'first_name': 'Nachito',
                'last_name': 'Zuñiga',
                'email': 'nachito@correo.cl',
                'password': 'Nachito',
                'tipo_acceso': 'admin'
            },
            {
                'rut': '18.123.456-7',
                'first_name': 'Cony',
                'last_name': 'Contreras',
                'email': 'cony@correo.cl',
                'password': 'Cony',
                'tipo_acceso': 'profesor'
            }
        ]

        for user_data in users:
            hashed_password = bcrypt.hashpw(user_data['password'].encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
            user = CREDENCIAL(
                rut=user_data['rut'],
                first_name=user_data['first_name'],
                last_name=user_data['last_name'],
                email=user_data['email'],
                password=hashed_password,
                tipo_acceso=user_data['tipo_acceso']
            )
            db.session.add(user)
        db.session.commit()

# Setup CORS
CORS(app)

# Create the database and tables if they don't exist
time.sleep(10)
with app.app_context():
    db.create_all()

if __name__ == "__main__":
    with app.app_context():
        time.sleep(12)  # Asegúrate de que la base de datos esté lista
        db.create_all()
        initialize_default_users() #crea a los 3 usuarios por default 
        app.run(debug=True, host='0.0.0.0')