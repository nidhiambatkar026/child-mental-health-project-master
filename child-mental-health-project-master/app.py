from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import os
from datetime import datetime, timedelta
from sqlalchemy import func, case
import os.path
from flask_migrate import Migrate

app = Flask(__name__)
app.config['SECRET_KEY'] = os.urandom(24).hex()
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{os.path.join(os.path.dirname(os.path.abspath(__file__)), "instance", "shorts.db")}'
app.config['UPLOAD_FOLDER'] = 'static/uploads'
ALLOWED_EXTENSIONS = {'mp4', 'mov', 'avi'}

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# Add after creating the db
migrate = Migrate(app, db)

# Models
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(120), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    warning_level = db.Column(db.Integer, default=0)
    last_warning_date = db.Column(db.DateTime)

class Video(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    filename = db.Column(db.String(200), nullable=False)
    upload_date = db.Column(db.DateTime, default=datetime.utcnow)
    views = db.Column(db.Integer, default=0)

class VideoAnalytics(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    video_id = db.Column(db.Integer, db.ForeignKey('video.id'), nullable=False)
    watch_duration = db.Column(db.Float, default=0)  # Duration watched in seconds
    completed = db.Column(db.Boolean, default=False)
    watch_date = db.Column(db.DateTime, default=datetime.utcnow)
    
    user = db.relationship('User', backref='video_analytics')
    video = db.relationship('Video', backref='analytics')

class EmotionAnalytics(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    video_id = db.Column(db.Integer, db.ForeignKey('video.id'), nullable=False)
    timestamp = db.Column(db.Float, nullable=False)  # Time in video when emotion was captured
    happy = db.Column(db.Float, default=0)
    sad = db.Column(db.Float, default=0)
    angry = db.Column(db.Float, default=0)
    surprised = db.Column(db.Float, default=0)
    neutral = db.Column(db.Float, default=0)
    recorded_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref='emotion_analytics')
    video = db.relationship('Video', backref='emotion_analytics')

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Routes
@app.route('/')
@login_required
def index():
    videos = Video.query.order_by(Video.upload_date.desc()).all()
    return render_template('index.html', videos=videos)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            return redirect(url_for('index'))
        flash('Invalid username or password')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        
        if User.query.filter_by(username=username).first():
            flash('Username already exists')
            return redirect(url_for('register'))
            
        user = User(
            username=username,
            email=email,
            password_hash=generate_password_hash(password)
        )
        db.session.add(user)
        db.session.commit()
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/admin')
@login_required
def admin():
    if not current_user.is_admin:
        return redirect(url_for('index'))
    videos = Video.query.all()
    return render_template('admin.html', videos=videos)

@app.route('/upload', methods=['POST'])
@login_required
def upload_video():
    if not current_user.is_admin:
        return redirect(url_for('index'))
        
    if 'video' not in request.files:
        flash('No video file')
        return redirect(url_for('admin'))
        
    file = request.files['video']
    if file.filename == '':
        flash('No selected file')
        return redirect(url_for('admin'))
        
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        
        video = Video(
            title=request.form.get('title'),
            filename=filename
        )
        db.session.add(video)
        db.session.commit()
        flash('Video uploaded successfully')
        
    return redirect(url_for('admin'))

@app.route('/delete_video/<int:video_id>')
@login_required
def delete_video(video_id):
    if not current_user.is_admin:
        return redirect(url_for('index'))
        
    video = Video.query.get_or_404(video_id)
    os.remove(os.path.join(app.config['UPLOAD_FOLDER'], video.filename))
    db.session.delete(video)
    db.session.commit()
    flash('Video deleted successfully')
    return redirect(url_for('admin'))

@app.route('/increment_view/<int:video_id>', methods=['POST'])
@login_required
def increment_view(video_id):
    video = Video.query.get_or_404(video_id)
    video.views += 1
    db.session.commit()
    return jsonify({'success': True, 'views': video.views})

@app.route('/track_view', methods=['POST'])
@login_required
def track_view():
    data = request.json
    video_id = data.get('video_id')
    duration = data.get('duration', 0)
    completed = data.get('completed', False)
    
    video = Video.query.get_or_404(video_id)
    
    # Create new analytics entry
    analytics = VideoAnalytics(
        user_id=current_user.id,
        video_id=video_id,
        watch_duration=duration,
        completed=completed
    )
    
    db.session.add(analytics)
    
    # Update video views only if it's a new view (not continuation)
    if duration < 1:  # New view
        video.views += 1
    
    db.session.commit()
    
    return jsonify({
        'success': True,
        'views': video.views
    })

@app.route('/analytics')
@login_required
def analytics():
    if not current_user.is_admin:
        return redirect(url_for('index'))
        
    # Get overall statistics
    total_views = VideoAnalytics.query.count()
    total_completed = VideoAnalytics.query.filter_by(completed=True).count()
    
    # Get video-specific statistics
    video_stats = db.session.query(
        Video,
        func.count(VideoAnalytics.id).label('view_count'),
        func.avg(VideoAnalytics.watch_duration).label('avg_duration'),
        func.count(case((VideoAnalytics.completed == True, 1))).label('completions')
    ).join(VideoAnalytics).group_by(Video.id).all()
    
    # Get user-specific statistics
    user_stats = db.session.query(
        User,
        func.count(VideoAnalytics.id).label('videos_watched'),
        func.sum(VideoAnalytics.watch_duration).label('total_watch_time')
    ).join(VideoAnalytics).group_by(User.id).all()
    
    return render_template('analytics.html',
                         total_views=total_views,
                         total_completed=total_completed,
                         video_stats=video_stats,
                         user_stats=user_stats)

def analyze_user_behavior(user_id):
    # Get recent emotion analytics for the user (last 30 minutes)
    recent_time = datetime.utcnow() - timedelta(minutes=30)
    recent_emotions = EmotionAnalytics.query.filter(
        EmotionAnalytics.user_id == user_id,
        EmotionAnalytics.recorded_at >= recent_time
    ).order_by(EmotionAnalytics.recorded_at.desc()).all()
    
    if not recent_emotions:
        return None
        
    # Calculate warning indicators
    warning_indicators = {
        'high_negative_emotions': False,
        'low_concentration': False,
        'reason': []
    }
    
    # Calculate average emotions
    total_records = len(recent_emotions)
    avg_angry = sum(e.angry for e in recent_emotions) / total_records
    avg_sad = sum(e.sad for e in recent_emotions) / total_records
    avg_neutral = sum(e.neutral for e in recent_emotions) / total_records
    
    # Check for high negative emotions
    if avg_angry > 0.4 or avg_sad > 0.4:
        warning_indicators['high_negative_emotions'] = True
        warning_indicators['reason'].append(
            "High levels of negative emotions detected"
        )
    
    # Check for low concentration (high neutral state)
    if avg_neutral > 0.6:
        warning_indicators['low_concentration'] = True
        warning_indicators['reason'].append(
            "Decreased concentration detected"
        )
    
    return warning_indicators

@app.route('/track_emotion', methods=['POST'])
@login_required
def track_emotion():
    data = request.json
    video_id = data.get('video_id')
    timestamp = data.get('timestamp')
    emotions = data.get('emotions', {})
    
    emotion_data = EmotionAnalytics(
        user_id=current_user.id,
        video_id=video_id,
        timestamp=timestamp,
        happy=emotions.get('happy', 0),
        sad=emotions.get('sad', 0),
        angry=emotions.get('angry', 0),
        surprised=emotions.get('surprised', 0),
        neutral=emotions.get('neutral', 0)
    )
    
    db.session.add(emotion_data)
    
    # Analyze user behavior
    warning_indicators = analyze_user_behavior(current_user.id)
    warning_status = None
    
    if warning_indicators:
        if warning_indicators['high_negative_emotions'] or warning_indicators['low_concentration']:
            current_user.warning_level += 1
            current_user.last_warning_date = datetime.utcnow()
            warning_status = {
                'level': current_user.warning_level,
                'reasons': warning_indicators['reason']
            }
    
    db.session.commit()
    
    return jsonify({
        'success': True,
        'warning': warning_status
    })

@app.route('/emotion_analytics')
@login_required
def emotion_analytics():
    if not current_user.is_admin:
        return redirect(url_for('index'))
    
    # Get overall emotion statistics per video
    video_emotions = db.session.query(
        Video,
        func.avg(EmotionAnalytics.happy).label('avg_happy'),
        func.avg(EmotionAnalytics.sad).label('avg_sad'),
        func.avg(EmotionAnalytics.angry).label('avg_angry'),
        func.avg(EmotionAnalytics.surprised).label('avg_surprised'),
        func.avg(EmotionAnalytics.neutral).label('avg_neutral')
    ).join(EmotionAnalytics, Video.id == EmotionAnalytics.video_id)\
    .group_by(Video.id).all()
    
    # Get user-specific emotion data
    user_emotions = db.session.query(
        User,
        Video,
        func.avg(EmotionAnalytics.happy).label('avg_happy'),
        func.avg(EmotionAnalytics.sad).label('avg_sad'),
        func.avg(EmotionAnalytics.angry).label('avg_angry'),
        func.avg(EmotionAnalytics.surprised).label('avg_surprised'),
        func.avg(EmotionAnalytics.neutral).label('avg_neutral'),
        func.count(EmotionAnalytics.id).label('total_reactions')
    ).select_from(EmotionAnalytics)\
    .join(User, User.id == EmotionAnalytics.user_id)\
    .join(Video, Video.id == EmotionAnalytics.video_id)\
    .group_by(User.id, Video.id).all()
    
    return render_template('emotion_analytics.html', 
                         video_emotions=video_emotions,
                         user_emotions=user_emotions)

if __name__ == '__main__':
    # Create instance directory if it doesn't exist
    instance_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'instance')
    if not os.path.exists(instance_path):
        os.makedirs(instance_path)
        print(f"Created instance directory: {instance_path}")

    db_file = os.path.join(instance_path, 'shorts.db')
    
    # Only initialize database if it doesn't exist
    if not os.path.exists(db_file):
        print("Initializing new database...")
        with app.app_context():
            # Create uploads directory if it doesn't exist
            if not os.path.exists(app.config['UPLOAD_FOLDER']):
                os.makedirs(app.config['UPLOAD_FOLDER'])
                print("Created uploads directory")
            
            # Create all tables
            db.create_all()
            print("Created database tables")
            
            try:
                # Create admin user
                admin = User(
                    username='admin',
                    email='admin@example.com',
                    password_hash=generate_password_hash('admin123'),
                    is_admin=True,
                    warning_level=0
                )
                db.session.add(admin)
                db.session.commit()
                print("Created admin user")
            except Exception as e:
                print(f"Error creating admin user: {e}")
                db.session.rollback()
    else:
        print(f"Using existing database: {db_file}")

    app.run(debug=True)
