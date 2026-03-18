from flask import Flask, flash, render_template, request, redirect, url_for, session, jsonify
from models import db, User, Habit, HabitCompletion
from datetime import date, timedelta
from functools import wraps
import os

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///habitu.db"
app.config["SECRET_KEY"] = os.urandom(24).hex()
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db.init_app(app)

with app.app_context():
    db.create_all()

# ── HABIT TEMPLATES ──────────────────────────────────────────
HABIT_TEMPLATES = [
    {"name": "Running", "icon": "🏃", "target": 5, "unit": "km", "color": "#e17055"},
    {"name": "Sleep", "icon": "😴", "target": 8, "unit": "hours", "color": "#6c5ce7"},
    {"name": "Water", "icon": "💧", "target": 8, "unit": "glasses", "color": "#00b894"},
    {"name": "Reading", "icon": "📖", "target": 30, "unit": "pages", "color": "#a29bfe"},
    {"name": "Meditation", "icon": "🧘", "target": 20, "unit": "minutes", "color": "#00cec9"},
    {"name": "Exercise", "icon": "💪", "target": 30, "unit": "minutes", "color": "#fd79a8"},
    {"name": "Healthy Eating", "icon": "🍎", "target": 5, "unit": "servings", "color": "#fdcb6e"},
    {"name": "Learning", "icon": "💻", "target": 60, "unit": "minutes", "color": "#74b9ff"},
]


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in first.", "warning")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


def get_current_user():
    return db.session.get(User, session.get("user_id"))


def get_habit_stats(habit, period="week"):
    """Calculate statistics for a habit over different periods.
    Periods: 'week', 'month', 'year'
    """
    today = date.today()
    stats = {
        "completed": 0,
        "total_days": 0,
        "total_value": 0,
        "avg_value": 0,
        "completion_rate": 0,
        "best_day": 0,
        "data": []
    }
    
    if period == "week":
        days_back = 7
        days_range = 6
    elif period == "month":
        days_back = 30
        days_range = 29
    else:  # year
        days_back = 365
        days_range = 364
    
    start_date = today - timedelta(days=days_back)
    completions = {c.completed_date: c for c in habit.completions if c.completed_date >= start_date}
    
    for i in range(days_range, -1, -1):
        day = today - timedelta(days=i)
        completion = completions.get(day)
        
        if completion:
            stats["completed"] += 1
            if habit.habit_type == "countable":
                stats["total_value"] += completion.value
                stats["best_day"] = max(stats["best_day"], completion.value)
                stats["data"].append({"date": day.isoformat(), "value": completion.value})
            else:
                stats["data"].append({"date": day.isoformat(), "completed": True})
        else:
            if habit.habit_type == "countable":
                stats["data"].append({"date": day.isoformat(), "value": 0})
            else:
                stats["data"].append({"date": day.isoformat(), "completed": False})
        
        stats["total_days"] += 1
    
    if stats["total_days"] > 0:
        stats["completion_rate"] = int((stats["completed"] / stats["total_days"]) * 100)
    
    if habit.habit_type == "countable" and stats["completed"] > 0:
        stats["avg_value"] = round(stats["total_value"] / stats["completed"], 2)
    
    return stats


# ── HOME ──────────────────────────────────────────────────────
@app.route("/")
def home():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    return render_template("index.html")


# ── REGISTER ──────────────────────────────────────────────────
@app.route("/auth/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")

        if not username or not email or not password:
            flash("All fields are required.", "error")
            return redirect(url_for("register"))

        if password != confirm:
            flash("Passwords do not match.", "error")
            return redirect(url_for("register"))

        if len(password) < 8:
            flash("Password must be at least 8 characters.", "error")
            return redirect(url_for("register"))

        if User.query.filter_by(email=email).first():
            flash("An account with this email already exists.", "error")
            return redirect(url_for("register"))

        user = User(username=username, email=email)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        session["user_id"] = user.id
        flash(f"Welcome to Habitu, {username}! 🎉", "success")
        return redirect(url_for("dashboard"))

    return render_template("auth/register.html")


# ── LOGIN ─────────────────────────────────────────────────────
@app.route("/auth/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        user = User.query.filter_by(email=email).first()

        if not user or not user.check_password(password):
            flash("Invalid email or password.", "error")
            return redirect(url_for("login"))

        session["user_id"] = user.id
        flash(f"Welcome back, {user.username}!", "success")
        return redirect(url_for("dashboard"))

    return render_template("auth/login.html")


# ── DASHBOARD ─────────────────────────────────────────────────
@app.route("/dashboard")
@login_required
def dashboard():
    user = get_current_user()
    habits = Habit.query.filter_by(user_id=user.id).order_by(Habit.created_at.desc()).all()

    total_habits = len(habits)
    completed_today = sum(1 for h in habits if h.completed_today)
    completion_pct = int((completed_today / total_habits * 100)) if total_habits > 0 else 0
    best_streak = max((h.streak for h in habits), default=0)

    # Weekly data for chart (last 7 days)
    weekly_data = []
    today = date.today()
    for i in range(6, -1, -1):
        d = today - timedelta(days=i)
        count = sum(
            1 for h in habits
            if any(c.completed_date == d for c in h.completions)
        )
        weekly_data.append({
            "day": d.strftime("%a"),
            "date": d.isoformat(),
            "count": count
        })

    return render_template(
        "dashboard.html",
        user=user,
        habits=habits,
        total_habits=total_habits,
        completed_today=completed_today,
        completion_pct=completion_pct,
        best_streak=best_streak,
        weekly_data=weekly_data,
        today=today,
        templates=HABIT_TEMPLATES
    )

# ── QUICK ADD TEMPLATE ───────────────────────────────────
@app.route("/habit/add-template", methods=["POST"])
@login_required
def add_template_habit():
    template_name = request.form.get("template_name", "").strip()
    
    template = next((t for t in HABIT_TEMPLATES if t["name"] == template_name), None)
    if not template:
        flash("Template not found.", "error")
        return redirect(url_for("dashboard"))
    
    # Check if habit already exists
    existing = Habit.query.filter_by(
        user_id=session["user_id"],
        name=template["name"]
    ).first()
    
    if existing:
        flash(f'You already have a "{template["name"]}" habit!', "warning")
        return redirect(url_for("dashboard"))
    
    habit = Habit(
        user_id=session["user_id"],
        name=template["name"],
        icon=template["icon"],
        color=template["color"],
        habit_type="countable",
        target_value=template["target"],
        unit=template["unit"]
    )
    db.session.add(habit)
    db.session.commit()
    
    flash(f'🚀 Added "{template["name"]}" habit! Target: {template["target"]} {template["unit"]}/day', "success")
    return redirect(url_for("dashboard"))

# ── ADD HABIT ─────────────────────────────────────────────────
@app.route("/habit/add", methods=["POST"])
@login_required
def add_habit():
    name = request.form.get("name", "").strip()
    icon = request.form.get("icon", "✨")
    color = request.form.get("color", "#6c5ce7")
    habit_type = request.form.get("habit_type", "boolean")
    target_value = request.form.get("target_value", 0, type=float)
    unit = request.form.get("unit", "").strip()

    if not name:
        flash("Habit name is required.", "error")
        return redirect(url_for("dashboard"))

    if habit_type == "countable" and target_value <= 0:
        flash("Target value must be greater than 0.", "error")
        return redirect(url_for("dashboard"))

    habit = Habit(
        user_id=session["user_id"],
        name=name,
        icon=icon,
        color=color,
        habit_type=habit_type,
        target_value=target_value,
        unit=unit
    )
    db.session.add(habit)
    db.session.commit()

    flash(f'Habit "{name}" created! 🚀', "success")
    return redirect(url_for("dashboard"))


# ── TOGGLE HABIT COMPLETION ───────────────────────────────────
@app.route("/habit/<int:habit_id>/toggle", methods=["POST"])
@login_required
def toggle_habit(habit_id):
    habit = Habit.query.get_or_404(habit_id)
    if habit.user_id != session["user_id"]:
        flash("Unauthorized.", "error")
        return redirect(url_for("dashboard"))

    today = date.today()
    existing = HabitCompletion.query.filter_by(
        habit_id=habit_id, completed_date=today
    ).first()

    if habit.habit_type == "countable":
        # For countable habits, accept a value from the form
        value = request.form.get("value", 0, type=float)
        if existing:
            existing.value = value
            db.session.commit()
        else:
            completion = HabitCompletion(habit_id=habit_id, completed_date=today, value=value)
            db.session.add(completion)
            db.session.commit()

        if value >= habit.target_value:
            flash(f'🎉 Target reached! "{habit.name}" — {value} {habit.unit}!', "success")
        else:
            flash(f'Logged {value} {habit.unit} for "{habit.name}".', "info")
    else:
        # Boolean toggle
        if existing:
            db.session.delete(existing)
            db.session.commit()
            flash(f'Unmarked "{habit.name}" for today.', "info")
        else:
            completion = HabitCompletion(habit_id=habit_id, completed_date=today)
            db.session.add(completion)
            db.session.commit()
            flash(f'Great job! "{habit.name}" completed! 🔥', "success")

    return redirect(url_for("dashboard"))


# ── DELETE HABIT ──────────────────────────────────────────────
@app.route("/habit/<int:habit_id>/delete", methods=["POST"])
@login_required
def delete_habit(habit_id):
    habit = Habit.query.get_or_404(habit_id)
    if habit.user_id != session["user_id"]:
        flash("Unauthorized.", "error")
        return redirect(url_for("dashboard"))

    name = habit.name
    db.session.delete(habit)
    db.session.commit()
    flash(f'Habit "{name}" deleted.', "info")
    return redirect(url_for("dashboard"))


# ── LOGOUT ────────────────────────────────────────────────────
@app.route("/logout")
def logout():
    session.clear()
    flash("You've been logged out.", "info")
    return redirect(url_for("home"))

# ── HABIT STATISTICS API ──────────────────────────────────────
@app.route("/api/habit/<int:habit_id>/stats", methods=["GET"])
@login_required
def get_habit_statistics(habit_id):
    habit = Habit.query.get_or_404(habit_id)
    if habit.user_id != session["user_id"]:
        return jsonify({"error": "Unauthorized"}), 403
    
    period = request.args.get("period", "week")  # week, month, year
    stats = get_habit_stats(habit, period)
    
    return jsonify({
        "habit_id": habit.id,
        "habit_name": habit.name,
        "period": period,
        "completed": stats["completed"],
        "total_days": stats["total_days"],
        "completion_rate": stats["completion_rate"],
        "total_value": round(stats["total_value"], 2),
        "avg_value": stats["avg_value"],
        "best_day": round(stats["best_day"], 2),
        "data": stats["data"]
    })

if __name__ == "__main__":
    app.run(debug=True)
