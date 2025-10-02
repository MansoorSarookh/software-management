import streamlit as st
import pandas as pd
from datetime import datetime, date, timedelta
from sqlalchemy import create_engine, Column, Integer, String, DateTime, ForeignKey, Boolean, Float, Text
from sqlalchemy.orm import sessionmaker, relationship, declarative_base
from sqlalchemy.exc import IntegrityError
import hashlib
import time
import plotly.express as px
import io
import base64

# --- Configuration & Setup ---

# Set Streamlit page configuration
st.set_page_config(
    page_title="Production-Ready Project Manager (Complete)",
    page_icon="🛠️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- Database Core (SQLAlchemy ORM) ---
# Using SQLite for the demo, easily scalable to PostgreSQL.
DATABASE_URL = "sqlite:///project_manager_complete.db"
# IMPORTANT for SQLite in Streamlit/Colab: check_same_thread must be False
Engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
Base = declarative_base()

# --- Database Models ---

class User(Base):
    """Database model for application users and team members."""
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True, nullable=False)
    email = Column(String, unique=True, nullable=False)
    password_hash = Column(String, nullable=False)
    role = Column(String, default="Team Member") # Admin, Project Manager, Team Member, Viewer
    created_at = Column(DateTime, default=datetime.now)

    projects = relationship("Project", back_populates="manager")
    tasks_assigned = relationship("Task", back_populates="assigned_to_user")
    time_logs = relationship("TimeLog", back_populates="user")
    risks_owned = relationship("Risk", back_populates="owner")

class Project(Base):
    """Database model for projects."""
    __tablename__ = 'projects'
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    description = Column(String)
    category = Column(String, default="Software")
    status = Column(String, default="Planning") # Planning, In Progress, Completed, Archived
    priority = Column(String, default="Medium") # Low, Medium, High
    start_date = Column(DateTime, default=datetime.now)
    due_date = Column(DateTime)
    manager_id = Column(Integer, ForeignKey('users.id'))

    manager = relationship("User", back_populates="projects")
    tasks = relationship("Task", back_populates="project", cascade="all, delete-orphan")
    sprints = relationship("Sprint", back_populates="project", cascade="all, delete-orphan")
    risks = relationship("Risk", back_populates="project", cascade="all, delete-orphan")

class Task(Base):
    """Database model for individual tasks."""
    __tablename__ = 'tasks'
    id = Column(Integer, primary_key=True)
    title = Column(String, nullable=False)
    # FIX: Corrected the typo where 'Column' was reassigned as a variable
    description = Column(Text) 
    status = Column(String, default="To Do") # To Do, In Progress, In Review, Done
    priority = Column(String, default="Medium") # Low, Medium, High, Urgent
    estimate_hours = Column(Float, default=0.0)
    dependency_task_id = Column(Integer, ForeignKey('tasks.id'), nullable=True) # For WBS/Dependencies
    sprint_id = Column(Integer, ForeignKey('sprints.id'), nullable=True) # For Sprint Planning
    project_id = Column(Integer, ForeignKey('projects.id'))
    assigned_to_id = Column(Integer, ForeignKey('users.id'))
    created_at = Column(DateTime, default=datetime.now)

    project = relationship("Project", back_populates="tasks")
    assigned_to_user = relationship("User", back_populates="tasks_assigned")
    time_logs = relationship("TimeLog", back_populates="task", cascade="all, delete-orphan")
    sprint = relationship("Sprint", back_populates="tasks")
    
    # Self-referencing relationship for dependencies
    depends_on = relationship("Task", remote_side=[id], backref="dependent_tasks")

class TimeLog(Base):
    """Database model for recording time spent on tasks."""
    __tablename__ = 'time_logs'
    id = Column(Integer, primary_key=True)
    hours = Column(Float, nullable=False)
    log_date = Column(DateTime, default=datetime.now)
    task_id = Column(Integer, ForeignKey('tasks.id'))
    user_id = Column(Integer, ForeignKey('users.id'))

    task = relationship("Task", back_populates="time_logs")
    user = relationship("User", back_populates="time_logs")

class Risk(Base):
    """Database model for the project risk register."""
    __tablename__ = 'risks'
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    description = Column(Text)
    probability = Column(String, default="Low") # Low, Medium, High
    impact = Column(String, default="Low") # Low, Medium, High
    mitigation_plan = Column(Text)
    status = Column(String, default="Open") # Open, Managed, Closed
    project_id = Column(Integer, ForeignKey('projects.id'))
    owner_id = Column(Integer, ForeignKey('users.id'))

    project = relationship("Project", back_populates="risks")
    owner = relationship("User", back_populates="risks_owned")

class Sprint(Base):
    """Database model for sprints (iterations)."""
    __tablename__ = 'sprints'
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    start_date = Column(DateTime)
    end_date = Column(DateTime)
    project_id = Column(Integer, ForeignKey('projects.id'))
    status = Column(String, default="Planning") # Planning, Active, Completed

    project = relationship("Project", back_populates="sprints")
    tasks = relationship("Task", back_populates="sprint")


# --- Database Manager & Seeding ---

class DatabaseManager:
    """Manages database connection and CRUD operations."""
    def __init__(self):
        self.Session = sessionmaker(bind=Engine)
        self.session = self.Session()
        self._ensure_db_schema()
        self._seed_initial_data()

    def _ensure_db_schema(self):
        """Ensures the database schema is created."""
        Base.metadata.create_all(Engine)

    def _seed_initial_data(self):
        """Creates initial admin and demo users if they don't exist."""
        def hash_password(password):
            return hashlib.sha256(password.encode()).hexdigest()

        if self.session.query(User).filter_by(username='admin').first() is None:
            admin = User(username='admin', email='admin@tool.com', password_hash=hash_password('adminpass'), role='Admin')
            manager = User(username='manager', email='manager@tool.com', password_hash=hash_password('managerpass'), role='Project Manager')
            member = User(username='member', email='member@tool.com', password_hash=hash_password('memberpass'), role='Team Member')
            self.session.add_all([admin, manager, member])
            self.session.commit()
            st.toast("Initial users created: admin, manager, member", icon="🔑")

        if self.session.query(Project).count() == 0:
            admin = self.session.query(User).filter_by(username='admin').first()
            manager_user = self.session.query(User).filter_by(username='manager').first()
            member_user = self.session.query(User).filter_by(username='member').first()

            proj_core = Project(name="Tool Core Development", description="Develop the core features and database.", category="Software", status="In Progress", priority="High", due_date=datetime.now() + timedelta(days=90), manager_id=manager_user.id)
            proj_marketing = Project(name="Q4 Marketing Strategy", description="Plan and execute holiday marketing campaign.", category="Marketing", status="Planning", priority="Medium", due_date=datetime.now() + timedelta(days=45), manager_id=admin.id)
            self.session.add_all([proj_core, proj_marketing])
            self.session.commit()

            # Create Sprint
            sprint_1 = Sprint(name="Sprint 1: Auth & DB", project_id=proj_core.id, start_date=datetime.now(), end_date=datetime.now() + timedelta(days=14), status="Active")
            self.session.add(sprint_1)
            self.session.commit()

            # Create Tasks
            task1 = Task(title="Implement Kanban View", status="In Progress", priority="Urgent", estimate_hours=8, project_id=proj_core.id, assigned_to_id=member_user.id, sprint_id=sprint_1.id)
            task2 = Task(title="Design Database Schema", status="Done", priority="High", estimate_hours=12, project_id=proj_core.id, assigned_to_id=admin.id)
            task3 = Task(title="Launch User Testing Phase 1", status="To Do", priority="High", estimate_hours=20, project_id=proj_marketing.id, assigned_to_id=manager_user.id)
            self.session.add_all([task1, task2, task3])
            self.session.commit()
            
            # Set dependency: task1 depends on task2
            task1.dependency_task_id = task2.id
            self.session.commit()
            
            # Create Risk
            risk1 = Risk(name="Database Migration Failure", description="Risk of data loss during production database switch.", probability="High", impact="High", mitigation_plan="Perform dry run migration and full backup.", project_id=proj_core.id, owner_id=admin.id)
            self.session.add(risk1)
            
            # Create Time Log
            log1 = TimeLog(hours=4.5, task_id=task2.id, user_id=admin.id)
            self.session.add(log1)
            
            self.session.commit()
            st.toast("Demo data (Projects, Sprints, Tasks, Risks, Time Logs) created.", icon="🚀")

    # --- Generic CRUD Methods ---
    def create(self, entity):
        try:
            self.session.add(entity)
            self.session.commit()
            return True
        except IntegrityError:
            self.session.rollback()
            return False
        except Exception as e:
            st.error(f"Database error: {e}")
            self.session.rollback()
            return False

    def read_all(self, model, project_id=None):
        if project_id and hasattr(model, 'project_id'):
            return self.session.query(model).filter(model.project_id == project_id).all()
        return self.session.query(model).all()

    def read_by_id(self, model, id):
        return self.session.query(model).get(id)

    def update(self, entity):
        try:
            self.session.merge(entity)
            self.session.commit()
            return True
        except Exception as e:
            st.error(f"Database error: {e}")
            self.session.rollback()
            return False

    def delete(self, entity):
        try:
            self.session.delete(entity)
            self.session.commit()
            return True
        except Exception as e:
            st.error(f"Database error: {e}")
            self.session.rollback()
            return False
            
    def get_users_for_assignment(self):
        users = self.session.query(User).all()
        return {user.username: user.id for user in users}

    def get_user_id_by_username(self, username):
        user = self.session.query(User).filter_by(username=username).first()
        return user.id if user else None

    def get_total_logged_hours(self, task_id):
        logs = self.session.query(TimeLog).filter(TimeLog.task_id == task_id).all()
        return sum(log.hours for log in logs)

# --- Authentication Service ---

class AuthService:
    """Handles user authentication and session state management."""
    def __init__(self, db_manager):
        self.db = db_manager

    def hash_password(self, password):
        return hashlib.sha256(password.encode()).hexdigest()

    def authenticate(self, username, password):
        user = self.db.session.query(User).filter_by(username=username).first()
        if user and user.password_hash == self.hash_password(password):
            st.session_state.is_authenticated = True
            st.session_state.username = user.username
            st.session_state.user_role = user.role
            st.session_state.user_id = user.id
            st.session_state.current_page = "Dashboard"
            st.toast(f"Welcome back, {user.username} ({user.role})!", icon="👋")
            return True
        return False

    def check_role_access(self, required_roles):
        return st.session_state.get('user_role') in required_roles

    def logout(self):
        st.session_state.clear()
        st.session_state.is_authenticated = False
        st.session_state.current_page = "Login"
        st.experimental_rerun()


# --- Streamlit UI Components & Utilities ---

def init_session_state():
    """Initialize necessary session state variables."""
    if 'is_authenticated' not in st.session_state:
        st.session_state.is_authenticated = False
        st.session_state.current_page = "Login"
        st.session_state.username = None
        st.session_state.user_role = None
        st.session_state.user_id = None
        st.session_state.show_task_form = False # For Kanban task creation

def get_db_and_auth():
    """Utility to get initialized DB and Auth services."""
    if 'db_manager' not in st.session_state:
        st.session_state.db_manager = DatabaseManager()
    if 'auth_service' not in st.session_state:
        st.session_state.auth_service = AuthService(st.session_state.db_manager)
    return st.session_state.db_manager, st.session_state.auth_service

def draw_kpi_card(title, value, icon, color_code):
    """Draws a responsive, styled card for the dashboard."""
    st.markdown(f"""
    <div style='
        background-color: #ffffff;
        padding: 15px;
        border-radius: 10px;
        box-shadow: 0 4px 10px rgba(0, 0, 0, 0.1);
        text-align: left;
        border-left: 6px solid {color_code};
        height: 100%;
    '>
        <p style='margin: 0; font-size: 0.9rem; color: #555;'>{icon} {title}</p>
        <h3 style='margin: 5px 0 0 0; font-size: 2.0rem; color: #1e40af; font-weight: 700;'>{value}</h3>
    </div>
    """, unsafe_allow_html=True)

# --- Visualizations ---

def get_gantt_chart(tasks):
    """Generates a Plotly Gantt chart from task data."""
    if not tasks:
        return None

    df_data = []
    for task in tasks:
        logged_hours = st.session_state.db_manager.get_total_logged_hours(task.id)
        # For simplicity, calculate end date based on logged time and a generic assumption
        # In a real app, this would use due_date and complex scheduling logic.
        start = task.created_at.date()
        end = start + timedelta(hours=task.estimate_hours) if task.estimate_hours > 0 else start + timedelta(days=1)
        
        df_data.append(dict(
            Task=task.title, 
            Start=start, 
            Finish=end.date(), 
            Resource=task.assigned_to_user.username,
            Status=task.status,
            Priority=task.priority,
            Duration=task.estimate_hours,
            Logged=logged_hours
        ))

    df = pd.DataFrame(df_data)
    
    # Map status to color
    status_colors = {
        "To Do": "#ef4444", "In Progress": "#f97316", "In Review": "#6366f1", "Done": "#10b981"
    }

    fig = px.timeline(
        df, 
        x_start="Start", 
        x_end="Finish", 
        y="Task", 
        color="Status",
        color_discrete_map=status_colors,
        custom_data=['Resource', 'Priority', 'Duration', 'Logged']
    )

    fig.update_layout(
        title='Project Task Timeline (Gantt Chart)',
        xaxis_title="Timeline",
        yaxis_title="",
        hoverlabel=dict(bgcolor="white", font_size=12)
    )

    fig.update_traces(
        hovertemplate="<b>Task:</b> %{y}<br>" +
                      "<b>Assigned:</b> %{customdata[0]}<br>" +
                      "<b>Start:</b> %{x}<br>" +
                      "<b>End:</b> %{xend}<br>" +
                      "<b>Priority:</b> %{customdata[1]}<br>" +
                      "<b>Estimated:</b> %{customdata[2]} hrs<br>" +
                      "<b>Logged:</b> %{customdata[3]} hrs<extra></extra>"
    )
    
    return fig

# --- Page Functions ---

def login_page(auth_service):
    """The login and registration page."""
    st.title("🔑 Project Management Tool Access")
    
    col1, col2 = st.columns([1, 1], gap="large")

    with col1:
        st.subheader("Existing User Login")
        with st.form("login_form"):
            username = st.text_input("Username", key="login_user")
            password = st.text_input("Password", type="password", key="login_pass")
            submitted = st.form_submit_button("Login", type="primary")

            if submitted:
                if auth_service.authenticate(username, password):
                    st.experimental_rerun()
                else:
                    st.error("Invalid username or password.")
    
    with col2:
        st.subheader("New User Registration")
        st.info("Registration is open for Project Manager or Team Member roles.")
        with st.form("register_form"):
            new_username = st.text_input("Choose Username", key="reg_user")
            new_email = st.text_input("Email", key="reg_email")
            new_password = st.text_input("Set Password", type="password", key="reg_pass")
            confirm_password = st.text_input("Confirm Password", type="password", key="reg_confirm_pass")
            role_options = ["Team Member", "Project Manager"]
            new_role = st.selectbox("Your Role", role_options, index=0, key="reg_role")
            
            register_submitted = st.form_submit_button("Register")
            
            if register_submitted:
                if not all([new_username, new_email, new_password, confirm_password]):
                    st.error("All fields are required.")
                elif new_password != confirm_password:
                    st.error("Passwords do not match.")
                else:
                    db_manager = st.session_state.db_manager
                    hashed_pass = auth_service.hash_password(new_password)
                    new_user = User(
                        username=new_username, email=new_email, password_hash=hashed_pass, role=new_role
                    )
                    if db_manager.create(new_user):
                        st.success("Registration successful! Please log in.")
                    else:
                        st.error("Username or Email already exists.")


def dashboard_page(db_manager):
    """The main user dashboard/landing page with KPIs and charts."""
    st.title("📊 Personal & Portfolio Dashboard")
    st.markdown(f"### Welcome, {st.session_state.username} ({st.session_state.user_role})!")
    
    all_projects = db_manager.read_all(Project)
    all_tasks = db_manager.read_all(Task)
    
    # Filter tasks assigned to the current user
    user_tasks = [t for t in all_tasks if t.assigned_to_id == st.session_state.user_id]
    
    # Calculate key metrics
    total_projects = len(all_projects)
    projects_active = len([p for p in all_projects if p.status == 'In Progress'])
    my_tasks_open = len([t for t in user_tasks if t.status != 'Done'])
    my_tasks_done = len([t for t in user_tasks if t.status == 'Done'])
    total_hours_logged = sum(log.hours for log in db_manager.read_all(TimeLog) if log.user_id == st.session_state.user_id)
    
    # KPI Cards
    col1, col2, col3, col4, col5 = st.columns(5)
    with col1: draw_kpi_card("Total Projects", total_projects, "📦", '#3b82f6')
    with col2: draw_kpi_card("Active Projects", projects_active, "📈", '#10b981')
    with col3: draw_kpi_card("My Open Tasks", my_tasks_open, "🔥", '#f97316')
    with col4: draw_kpi_card("My Done Tasks", my_tasks_done, "✅", '#6366f1')
    with col5: draw_kpi_card("Hours Logged", f"{total_hours_logged:.1f}h", "⏱️", '#d946ef')

    st.markdown("---")

    col_chart, col_summary = st.columns([2, 1])

    with col_chart:
        st.subheader("Team Task Status Breakdown")
        if all_tasks:
            task_status_df = pd.DataFrame([{'Status': t.status} for t in all_tasks])
            status_counts = task_status_df['Status'].value_counts().reset_index()
            status_counts.columns = ['Status', 'Count']
            
            fig = px.bar(status_counts, 
                         x='Status', 
                         y='Count', 
                         color='Status',
                         color_discrete_map={"To Do": "#ef4444", "In Progress": "#f97316", "In Review": "#6366f1", "Done": "#10b981"},
                         title="Overall Task Status Distribution")
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No tasks to display.")

    with col_summary:
        st.subheader("Critical Project Info")
        
        # Display risks
        risks = db_manager.read_all(Risk)
        st.metric(label="Total Open Risks", value=len([r for r in risks if r.status == 'Open']))
        
        # Display high priority tasks
        high_tasks = [t for t in all_tasks if t.priority in ['High', 'Urgent'] and t.status != 'Done']
        st.metric(label="Urgent/High Priority Tasks", value=len(high_tasks))

        st.markdown("**Urgent Tasks**")
        for t in high_tasks[:5]:
            st.markdown(f"- **{t.title}** ({t.project.name})")


def projects_page(db_manager):
    """Page for Project CRUD and sub-feature navigation."""
    st.title("📦 Project Management (CRUD)")

    if st.session_state.user_role not in ['Admin', 'Project Manager']:
        st.warning("You do not have permission to manage projects. Viewing mode only.")

    tab1, tab2 = st.tabs(["View/Edit Projects", "Create New Project"])
    
    with tab1:
        projects = db_manager.read_all(Project)
        project_data = []
        for p in projects:
            manager_username = p.manager.username if p.manager else "N/A"
            total_tasks = len(p.tasks)
            completed_tasks = len([t for t in p.tasks if t.status == 'Done'])
            
            project_data.append({
                'ID': p.id, 'Name': p.name, 'Manager': manager_username, 'Status': p.status, 
                'Priority': p.priority, 'Tasks': f"{completed_tasks}/{total_tasks}", 
                'Due Date': p.due_date.strftime('%Y-%m-%d') if p.due_date else 'N/A'
            })
        
        df = pd.DataFrame(project_data)
        st.dataframe(df, use_container_width=True, hide_index=True)

        st.markdown("---")
        st.subheader("Edit/Delete Project")

        project_ids = [p.id for p in projects]
        if project_ids:
            selected_id = st.selectbox("Select Project ID to Edit/Delete", project_ids, key="proj_select_edit")
            selected_project = db_manager.read_by_id(Project, selected_id)
            
            if selected_project:
                with st.expander(f"Edit Project: {selected_project.name}", expanded=False):
                    if st.session_state.user_role in ['Admin', 'Project Manager']:
                        users_map = db_manager.get_users_for_assignment()
                        current_manager_name = db_manager.read_by_id(User, selected_project.manager_id).username
                        
                        with st.form(f"edit_project_form_{selected_id}"):
                            new_name = st.text_input("Project Name", value=selected_project.name)
                            new_desc = st.text_area("Description", value=selected_project.description)
                            new_status = st.selectbox("Status", ['Planning', 'In Progress', 'Completed', 'Archived'], index=['Planning', 'In Progress', 'Completed', 'Archived'].index(selected_project.status))
                            new_priority = st.selectbox("Priority", ['Low', 'Medium', 'High'], index=['Low', 'Medium', 'High'].index(selected_project.priority))
                            new_manager_name = st.selectbox("Project Manager", list(users_map.keys()), index=list(users_map.keys()).index(current_manager_name))
                            
                            col_e1, col_e2 = st.columns(2)
                            with col_e1: update_submitted = st.form_submit_button("Update Project", type="primary")
                            with col_e2: delete_submitted = st.form_submit_button("Delete Project", type="danger")

                            if update_submitted:
                                selected_project.name, selected_project.description, selected_project.status, selected_project.priority, selected_project.manager_id = new_name, new_desc, new_status, new_priority, users_map[new_manager_name]
                                if db_manager.update(selected_project):
                                    st.success(f"Project '{selected_project.name}' updated successfully!")
                                    time.sleep(1); st.experimental_rerun()
                                else: st.error("Failed to update project.")

                            if delete_submitted:
                                if db_manager.delete(selected_project):
                                    st.success(f"Project '{selected_project.name}' and all associated data deleted.")
                                    time.sleep(1); st.experimental_rerun()
                                else: st.error("Failed to delete project.")
                    else:
                        st.warning("Insufficient permissions to edit or delete projects.")
        else:
             st.info("No projects created yet.")

    with tab2:
        if st.session_state.user_role in ['Admin', 'Project Manager']:
            users_map = db_manager.get_users_for_assignment()
            with st.form("new_project_form"):
                project_name = st.text_input("Project Name (Required)")
                project_desc = st.text_area("Description")
                col_c1, col_c2, col_c3 = st.columns(3)
                with col_c1: project_manager_name = st.selectbox("Project Manager", list(users_map.keys()))
                with col_c2: project_priority = st.selectbox("Priority", ['Low', 'Medium', 'High'])
                with col_c3: project_due_date = st.date_input("Due Date", min_value=date.today())
                create_submitted = st.form_submit_button("Create Project", type="primary")

                if create_submitted:
                    if not project_name: st.error("Project Name is required.")
                    else:
                        new_project = Project(name=project_name, description=project_desc, priority=project_priority, 
                                            due_date=datetime.combine(project_due_date, datetime.min.time()), 
                                            manager_id=users_map[project_manager_name])
                        if db_manager.create(new_project):
                            st.success(f"Project '{project_name}' created successfully!"); time.sleep(1); st.experimental_rerun()
                        else: st.error("Failed to create project.")
        else:
            st.warning("You must be an Admin or Project Manager to create new projects.")


def kanban_page(db_manager):
    """Page for Task Management, Kanban View, and Time Logging."""
    st.title("📋 Kanban Board & Tasks")

    all_projects = db_manager.read_all(Project)
    project_options = {p.name: p.id for p in all_projects}
    
    col_sel, col_add = st.columns([3, 1])

    with col_sel:
        selected_project_name = st.selectbox("Select Project for Kanban View", 
                                             list(project_options.keys()) if project_options else ["No Projects Available"],
                                             key="kanban_project_select")

    if not selected_project_name or selected_project_name == "No Projects Available":
        st.info("Please create a project first on the 'Project Management' page.")
        return

    selected_project_id = project_options[selected_project_name]
    tasks = db_manager.read_all(Task, project_id=selected_project_id)
    sprint_options = db_manager.read_all(Sprint, project_id=selected_project_id)
    sprint_map = {s.name: s.id for s in sprint_options}

    # --- Task Creation Sidebar/Expander ---
    with col_add:
        if st.session_state.user_role in ['Admin', 'Project Manager']:
            if st.button("➕ Add New Task", use_container_width=True, type="primary"):
                st.session_state.show_task_form = True

    if st.session_state.get('show_task_form', False):
        with st.sidebar:
            st.subheader(f"Add Task to {selected_project_name}")
            users_map = db_manager.get_users_for_assignment()
            
            with st.form("new_task_form"):
                task_title = st.text_input("Task Title (Required)")
                task_desc = st.text_area("Description")
                
                col_i1, col_i2 = st.columns(2)
                with col_i1:
                    task_assigned_name = st.selectbox("Assign To", list(users_map.keys()))
                with col_i2:
                    task_priority = st.selectbox("Priority", ['Low', 'Medium', 'High', 'Urgent'])
                
                col_i3, col_i4 = st.columns(2)
                with col_i3:
                    task_estimate = st.number_input("Estimate (Hours)", min_value=0.0, value=4.0, step=0.5)
                with col_i4:
                    sprint_name = st.selectbox("Assign to Sprint (Optional)", ["Backlog"] + list(sprint_map.keys()))
                
                # Dependencies Mock
                dependency_tasks = ["None"] + [f"Task #{t.id}: {t.title}" for t in tasks if t.status != 'Done']
                dependency_selection = st.selectbox("Depends on (Task Dependency)", dependency_tasks)
                
                col_b1, col_b2 = st.columns(2)
                with col_b1: create_task_submitted = st.form_submit_button("Create Task", type="primary")
                with col_b2:
                    if st.form_submit_button("Cancel"): st.session_state.show_task_form = False; st.experimental_rerun()
                        
                if create_task_submitted:
                    if not task_title: st.error("Task Title is required.")
                    else:
                        dependency_id = int(dependency_selection.split(':')[0].replace('Task #', '')) if dependency_selection != "None" else None
                        sprint_id = sprint_map.get(sprint_name)
                        new_task = Task(title=task_title, description=task_desc, priority=task_priority, 
                                        estimate_hours=task_estimate, project_id=selected_project_id, 
                                        assigned_to_id=users_map[task_assigned_name], 
                                        dependency_task_id=dependency_id, sprint_id=sprint_id)
                        if db_manager.create(new_task):
                            st.success(f"Task '{task_title}' created."); st.session_state.show_task_form = False; time.sleep(1); st.experimental_rerun()
                        else: st.error("Failed to create task.")
    
    # --- Kanban Board Rendering ---
    KANBAN_STATUSES = ["To Do", "In Progress", "In Review", "Done"]
    tasks_by_status = {status: [] for status in KANBAN_STATUSES}
    for task in tasks:
        if task.status in KANBAN_STATUSES: tasks_by_status[task.status].append(task)
            
    cols = st.columns(len(KANBAN_STATUSES))
    
    st.markdown("""
    <style>
    /* Custom CSS for Kanban Board Aesthetics */
    .kanban-card {
        background-color: #ffffff; padding: 10px; margin-bottom: 10px; border-radius: 8px;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1); border-left: 4px solid;
    }
    .kanban-header {
        text-align: center; padding: 10px; border-radius: 5px; margin-bottom: 15px;
        color: white; font-weight: bold; text-transform: uppercase; letter-spacing: 1px;
    }
    .status-todo { background-color: #ef4444; } .status-progress { background-color: #f97316; }
    .status-review { background-color: #6366f1; } .status-done { background-color: #10b981; }
    .priority-Urgent { border-color: #ef4444 !important; } .priority-High { border-color: #f59e0b !important; }
    .priority-Medium { border-color: #3b82f6 !important; } .priority-Low { border-color: #10b981 !important; }
    </style>
    """, unsafe_allow_html=True)
    
    for i, status in enumerate(KANBAN_STATUSES):
        with cols[i]:
            header_class = f"status-{status.lower().replace(' ', '-')}"
            st.markdown(f'<div class="kanban-header {header_class}">{status} ({len(tasks_by_status[status])})</div>', unsafe_allow_html=True)
            
            task_container = st.container(height=600, border=False) 
            
            for task in tasks_by_status[status]:
                logged_hours = db_manager.get_total_logged_hours(task.id)
                progress = logged_hours / task.estimate_hours if task.estimate_hours > 0 else 0
                
                # --- Card Content ---
                card_content = f"""
                <div class='kanban-card priority-{task.priority}'>
                    <small>📌 Task #{task.id} | Sprint: {task.sprint.name if task.sprint else 'Backlog'}</small>
                    <h5 style='margin-top: 5px; margin-bottom: 5px; font-weight: 600;'>{task.title}</h5>
                    <p style='font-size: 0.8rem; color: #666; margin-bottom: 5px;'>Assigned: <b>{task.assigned_to_user.username}</b></p>
                    <p style='font-size: 0.8rem; color: #666; margin-bottom: 5px;'>Est: {task.estimate_hours:.1f}h | Logged: {logged_hours:.1f}h</p>
                    <p style='font-size: 0.8rem; color: #666; margin-bottom: 5px;'>{task.depends_on.title if task.depends_on else ''}</p>
                """
                
                with task_container:
                    st.markdown(card_content, unsafe_allow_html=True)
                    
                    if st.session_state.user_role in ['Admin', 'Project Manager', 'Team Member']:
                        with st.form(f"update_task_{task.id}", clear_on_submit=False):
                            
                            col_up1, col_up2 = st.columns([2, 1])
                            with col_up1:
                                new_status = st.selectbox("Status", KANBAN_STATUSES, index=KANBAN_STATUSES.index(task.status), label_visibility="collapsed", key=f"status_select_{task.id}")
                            with col_up2:
                                hours_to_log = st.number_input("Log (h)", min_value=0.0, max_value=24.0, value=0.0, step=0.5, key=f"log_input_{task.id}", label_visibility="collapsed")
                            
                            col_b1, col_b2 = st.columns(2)
                            with col_b1:
                                if st.form_submit_button("Move & Log", type="secondary", use_container_width=True):
                                    task.status = new_status
                                    
                                    if hours_to_log > 0:
                                        new_log = TimeLog(hours=hours_to_log, task_id=task.id, user_id=st.session_state.user_id)
                                        db_manager.create(new_log)
                                    
                                    if db_manager.update(task):
                                        st.toast(f"Task #{task.id} moved to {new_status} and {hours_to_log}h logged!", icon="👍")
                                        time.sleep(0.5); st.experimental_rerun()
                                    else:
                                        st.error("Failed to update task.")
                            with col_b2:
                                if st.form_submit_button("View Details"):
                                    st.info(f"Task Details for #{task.id}: {task.description or 'No detailed description.'}")
                                    st.info(f"Current Dependencies: {task.depends_on.title if task.depends_on else 'None'}")


def sprint_page(db_manager):
    """Page for Sprint management and burndown chart analytics (mock)."""
    st.title("🏃 Sprint & Backlog Management")

    all_projects = db_manager.read_all(Project)
    project_options = {p.name: p.id for p in all_projects}

    selected_project_name = st.selectbox("Select Project for Sprint Planning", 
                                         list(project_options.keys()) if project_options else ["No Projects Available"],
                                         key="sprint_project_select")

    if not selected_project_name or selected_project_name == "No Projects Available": return

    selected_project_id = project_options[selected_project_name]

    col_s1, col_s2 = st.columns([2, 1])
    with col_s2:
        with st.expander("➕ Create New Sprint"):
            if st.session_state.user_role in ['Admin', 'Project Manager']:
                with st.form("new_sprint_form"):
                    sprint_name = st.text_input("Sprint Name (e.g., Sprint 3)")
                    sprint_start = st.date_input("Start Date", value=date.today())
                    sprint_end = st.date_input("End Date", value=date.today() + timedelta(days=14))
                    if st.form_submit_button("Create Sprint", type="primary"):
                        new_sprint = Sprint(name=sprint_name, project_id=selected_project_id, 
                                            start_date=datetime.combine(sprint_start, datetime.min.time()),
                                            end_date=datetime.combine(sprint_end, datetime.min.time()))
                        if db_manager.create(new_sprint):
                            st.success("Sprint created!"); time.sleep(0.5); st.experimental_rerun()
                        else: st.error("Failed to create sprint.")
            else: st.warning("Only Project Managers can create sprints.")
    
    sprints = db_manager.read_all(Sprint, project_id=selected_project_id)
    
    with col_s1:
        st.subheader("Project Sprints")
        sprint_data = []
        for s in sprints:
            tasks_count = len(s.tasks)
            completed_count = len([t for t in s.tasks if t.status == 'Done'])
            sprint_data.append({
                'ID': s.id, 'Name': s.name, 'Status': s.status, 'Tasks': f"{completed_count}/{tasks_count}",
                'Duration': f"{s.start_date.strftime('%Y-%m-%d')} to {s.end_date.strftime('%Y-%m-%d')}"
            })
        st.dataframe(pd.DataFrame(sprint_data), use_container_width=True, hide_index=True)


    st.markdown("---")
    st.subheader("Backlog & Task Assignment")
    
    # Tasks not assigned to a sprint are in the backlog (sprint_id is None)
    backlog_tasks = [t for t in db_manager.read_all(Task, project_id=selected_project_id) if not t.sprint]
    
    col_backlog, col_sprint_assign = st.columns(2)
    with col_backlog:
        st.markdown("#### Backlog Tasks")
        if backlog_tasks:
            backlog_df = pd.DataFrame([{'ID': t.id, 'Title': t.title, 'Est. Hrs': t.estimate_hours, 'Priority': t.priority} for t in backlog_tasks])
            st.dataframe(backlog_df, use_container_width=True, hide_index=True)
        else: st.info("The backlog is empty! All tasks are assigned to sprints.")

    with col_sprint_assign:
        st.markdown("#### Assign Task to Sprint")
        if sprints and backlog_tasks:
            sprint_names = {s.id: s.name for s in sprints}
            backlog_titles = {t.id: t.title for t in backlog_tasks}
            
            with st.form("assign_task_form"):
                task_to_assign = st.selectbox("Select Task from Backlog", list(backlog_titles.keys()), format_func=lambda x: backlog_titles[x])
                target_sprint = st.selectbox("Select Target Sprint", list(sprint_names.keys()), format_func=lambda x: sprint_names[x])
                
                if st.form_submit_button("Move to Sprint"):
                    task = db_manager.read_by_id(Task, task_to_assign)
                    task.sprint_id = target_sprint
                    if db_manager.update(task):
                        st.success(f"Task '{task.title}' moved to sprint '{sprint_names[target_sprint]}'."); time.sleep(0.5); st.experimental_rerun()
                    else: st.error("Failed to assign task.")
        elif sprints:
            st.info("No tasks in the backlog to assign.")
        else:
            st.warning("Create a sprint first to assign tasks.")


def gantt_page(db_manager):
    """Page for Gantt Chart visualization (WBS mock included)."""
    st.title("📈 Timeline & Work Breakdown Structure (WBS)")

    all_projects = db_manager.read_all(Project)
    project_options = {p.name: p.id for p in all_projects}

    selected_project_name = st.selectbox("Select Project for Visualization", 
                                         list(project_options.keys()) if project_options else ["No Projects Available"],
                                         key="gantt_project_select")

    if not selected_project_name or selected_project_name == "No Projects Available": return

    selected_project_id = project_options[selected_project_name]
    project_tasks = db_manager.read_all(Task, project_id=selected_project_id)

    # --- WBS/Dependencies Visualization Mock ---
    st.markdown("### Work Breakdown Structure (Dependency View)")
    if project_tasks:
        # Create a dictionary mapping task ID to task object
        tasks_map = {t.id: t for t in project_tasks}
        
        # Identify top-level tasks (tasks that no other task depends on, and have no dependency themselves)
        dependent_ids = {t.dependency_task_id for t in project_tasks if t.dependency_task_id}
        top_level_tasks = [t for t in project_tasks if t.id not in dependent_ids and not t.dependency_task_id]
        
        # Build dependency tree structure
        def render_wbs_node(task, level=0):
            prefix = "•" * (level + 1)
            status_emoji = "✅" if task.status == 'Done' else "🚧"
            st.markdown(f"#### {prefix} {status_emoji} **{task.title}** (Est: {task.estimate_hours}h, Prio: {task.priority})")

            # Find tasks that depend on the current task
            for dependent_task in [t for t in project_tasks if t.dependency_task_id == task.id]:
                render_wbs_node(dependent_task, level + 1)

        if top_level_tasks:
            st.info("Tasks are shown in order of completion (dependencies first).")
            for task in top_level_tasks:
                render_wbs_node(task)
        else:
            st.warning("No clear top-level tasks or dependencies found. All tasks might be independent.")
    else:
        st.info("No tasks available to generate WBS.")

    st.markdown("---")
    
    # --- Gantt Chart Visualization ---
    st.markdown("### Project Gantt Chart")
    fig = get_gantt_chart(project_tasks)
    if fig:
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No tasks available to render the Gantt chart.")

def risk_register_page(db_manager):
    """Page for managing project risks."""
    st.title("🚨 Risk Register")

    all_projects = db_manager.read_all(Project)
    project_options = {p.name: p.id for p in all_projects}
    users_map = db_manager.get_users_for_assignment()

    selected_project_name = st.selectbox("Select Project to Manage Risks", 
                                         list(project_options.keys()) if project_options else ["No Projects Available"],
                                         key="risk_project_select")

    if not selected_project_name or selected_project_name == "No Projects Available": return
    selected_project_id = project_options[selected_project_name]

    if st.session_state.user_role not in ['Admin', 'Project Manager']:
        st.warning("You must be an Admin or Project Manager to manage risks.")

    tab1, tab2 = st.tabs(["View Risks", "Add New Risk"])

    with tab1:
        risks = db_manager.read_all(Risk, project_id=selected_project_id)
        
        if risks:
            risk_data = []
            for r in risks:
                risk_data.append({
                    'ID': r.id, 'Name': r.name, 'Probability': r.probability, 
                    'Impact': r.impact, 'Status': r.status, 'Owner': r.owner.username
                })
            st.dataframe(pd.DataFrame(risk_data), use_container_width=True, hide_index=True)
            
            # Risk Mitigation Action
            st.markdown("---")
            st.subheader("Mitigation & Closure")
            risk_ids = [r.id for r in risks]
            selected_risk_id = st.selectbox("Select Risk ID to Manage", risk_ids)

            if selected_risk_id and st.session_state.user_role in ['Admin', 'Project Manager']:
                selected_risk = db_manager.read_by_id(Risk, selected_risk_id)
                with st.form(f"mitigation_form_{selected_risk_id}"):
                    st.markdown(f"**Risk:** {selected_risk.name}")
                    st.text_area("Mitigation Plan", value=selected_risk.mitigation_plan, key="mitigation_plan_edit")
                    new_status = st.selectbox("Status", ['Open', 'Managed', 'Closed'], index=['Open', 'Managed', 'Closed'].index(selected_risk.status))
                    
                    if st.form_submit_button("Update Risk"):
                        selected_risk.mitigation_plan = st.session_state[f"mitigation_plan_edit"]
                        selected_risk.status = new_status
                        if db_manager.update(selected_risk):
                            st.success("Risk updated successfully."); time.sleep(0.5); st.experimental_rerun()
                        else: st.error("Failed to update risk.")
        else:
            st.info("No risks registered for this project yet.")

    with tab2:
        if st.session_state.user_role in ['Admin', 'Project Manager']:
            with st.form("add_risk_form"):
                risk_name = st.text_input("Risk Title (Required)")
                risk_desc = st.text_area("Detailed Description")
                col_r1, col_r2 = st.columns(2)
                with col_r1: risk_prob = st.selectbox("Probability", ['Low', 'Medium', 'High'])
                with col_r2: risk_impact = st.selectbox("Impact", ['Low', 'Medium', 'High'])
                risk_owner_name = st.selectbox("Risk Owner", list(users_map.keys()))
                
                if st.form_submit_button("Register Risk", type="primary"):
                    if not risk_name: st.error("Risk Title is required.")
                    else:
                        new_risk = Risk(name=risk_name, description=risk_desc, probability=risk_prob, 
                                        impact=risk_impact, project_id=selected_project_id, 
                                        owner_id=users_map[risk_owner_name])
                        if db_manager.create(new_risk):
                            st.success("Risk successfully registered."); time.sleep(0.5); st.experimental_rerun()
                        else: st.error("Failed to register risk.")


def reports_page(db_manager):
    """Page for generating and exporting data reports."""
    st.title("📄 Reports and Analytics")
    
    tab1, tab2, tab3 = st.tabs(["Data Export", "Time Tracking Report", "Velocity Chart (Mock)"])

    # --- Data Export Tab ---
    with tab1:
        st.subheader("Data Export (CSV & JSON)")
        
        def convert_df_to_csv(df):
            # Function to convert DataFrame to CSV for download
            return df.to_csv(index=False).encode('utf-8')

        models = {'Projects': Project, 'Tasks': Task, 'Users': User, 'Time Logs': TimeLog, 'Risks': Risk}
        selected_model = st.selectbox("Select Data Entity to Export", list(models.keys()))
        
        data = db_manager.read_all(models[selected_model])
        
        if data:
            # Simple conversion to DataFrame, handling relationships for display
            df_export = pd.DataFrame([item.__dict__ for item in data])
            df_export = df_export.drop(columns=['_sa_instance_state'], errors='ignore')
            st.dataframe(df_export, use_container_width=True)
            
            csv = convert_df_to_csv(df_export)
            
            st.download_button(
                label=f"Download {selected_model} as CSV",
                data=csv,
                file_name=f'{selected_model.lower().replace(" ", "_")}_report_{datetime.now().strftime("%Y%m%d")}.csv',
                mime='text/csv',
                type="primary"
            )
            
            st.markdown("""
            > **PDF/Excel Export Note:** For PDF/Excel exports (`ReportLab`/`XlsxWriter`), you would use the `df_export` object, 
            > install the required libraries (e.g., `!pip install openpyxl`), and implement the conversion logic here.
            """)
        else:
            st.info("No data available for export.")

    # --- Time Tracking Report Tab ---
    with tab2:
        st.subheader("Team Time Tracking Summary")
        
        all_logs = db_manager.read_all(TimeLog)
        if all_logs:
            log_data = []
            for log in all_logs:
                log_data.append({
                    'User': log.user.username,
                    'Task ID': log.task.id,
                    'Task Title': log.task.title,
                    'Project': log.task.project.name,
                    'Hours Logged': log.hours,
                    'Date': log.log_date.strftime('%Y-%m-%d')
                })
            
            df_logs = pd.DataFrame(log_data)
            
            st.dataframe(df_logs.sort_values(by='Hours Logged', ascending=False), use_container_width=True, hide_index=True)

            # Plot Weekly Logged Hours
            df_logs['Week'] = pd.to_datetime(df_logs['Date']).dt.to_period('W').astype(str)
            weekly_summary = df_logs.groupby(['User', 'Week'])['Hours Logged'].sum().reset_index()
            
            fig = px.bar(weekly_summary, x="Week", y="Hours Logged", color="User", 
                         title="Weekly Logged Hours by Team Member")
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No time has been logged yet.")

    # --- Velocity Chart Tab (Mock) ---
    with tab3:
        st.subheader("Sprint Velocity Chart")
        st.warning("This is a functional mock. For true Burndown/Velocity, complex calculation of Story Points/Estimates within a sprint is required.")
        
        all_sprints = db_manager.read_all(Sprint)
        if all_sprints:
            velocity_data = []
            for s in all_sprints:
                if s.status == 'Completed':
                    completed_tasks = [t for t in s.tasks if t.status == 'Done']
                    # Velocity is sum of estimates of completed tasks
                    velocity = sum(t.estimate_hours for t in completed_tasks)
                    velocity_data.append({'Sprint': s.name, 'Project': s.project.name, 'Velocity (Hours)': velocity})
            
            if velocity_data:
                df_velocity = pd.DataFrame(velocity_data)
                fig_vel = px.bar(df_velocity, x="Sprint", y="Velocity (Hours)", color="Project", 
                                 title="Sprint Velocity (Hours Completed)",
                                 labels={'Velocity (Hours)': 'Completed Hours'})
                st.plotly_chart(fig_vel, use_container_width=True)
            else:
                st.info("No completed sprints with logged velocity data.")


def administration_page(db_manager):
    """Page for system settings and role management."""
    st.title("⚙️ Administration & Team Management")
    if not st.session_state.user_role == 'Admin':
        st.error("Access Denied. Only Administrators can view this page.")
        return

    tab1, tab2 = st.tabs(["Role Management", "System Settings (Mock)"])

    with tab1:
        st.subheader("User Role and Team Management")
        users = db_manager.read_all(User)
        user_data = [{
            'ID': u.id, 'Username': u.username, 'Email': u.email, 'Role': u.role
        } for u in users]
        
        st.dataframe(pd.DataFrame(user_data), use_container_width=True, hide_index=True)

        st.markdown("---")
        st.subheader("Update User Role")
        
        user_map = {u.username: u.id for u in users}
        selected_username = st.selectbox("Select User", list(user_map.keys()))

        if selected_username:
            user_to_update = db_manager.read_by_id(User, user_map[selected_username])
            
            with st.form("update_role_form"):
                new_role = st.selectbox("New Role", ['Admin', 'Project Manager', 'Team Member', 'Viewer'], index=['Admin', 'Project Manager', 'Team Member', 'Viewer'].index(user_to_update.role))
                if st.form_submit_button("Update Role", type="primary"):
                    user_to_update.role = new_role
                    if db_manager.update(user_to_update):
                        st.success(f"Role for {selected_username} updated to {new_role}.")
                        time.sleep(0.5); st.experimental_rerun()
                    else: st.error("Failed to update user role.")

    with tab2:
        st.subheader("System Settings and Audit Logs")
        st.info("This section is a placeholder for complex system configurations.")
        st.code("""
        # Example system settings structure
        SYSTEM_SETTINGS = {
            'DEFAULT_SPRINT_DAYS': 14,
            'MAX_PROJECTS_PER_MANAGER': 10,
            'AUDIT_LOGGING_ENABLED': True
        }
        """)


# --- Main Application Logic ---

def main_app():
    """Main function to run the Streamlit app."""
    
    init_session_state()
    db_manager, auth_service = get_db_and_auth()

    # --- Sidebar Navigation ---
    with st.sidebar:
        st.image("https://placehold.co/150x50/1e40af/ffffff?text=PM+TOOL", width=200)
        st.markdown("## Navigation")

        if st.session_state.is_authenticated:
            # Defined list of main pages
            main_pages = [
                "Dashboard", 
                "Project Management", 
                "Kanban Board", 
                "Sprint Management",
                "Gantt & WBS",
                "Risk Register",
                "Reports & Analytics"
            ]
            
            if st.session_state.user_role == 'Admin':
                main_pages.append("Administration")
            
            st.session_state.current_page = st.radio(
                "Go to:",
                options=main_pages,
                key="main_nav"
            )

            st.markdown("---")
            st.write(f"Logged in as: **{st.session_state.username}** ({st.session_state.user_role})")
            if st.button("Logout", type="secondary", use_container_width=True):
                auth_service.logout()
        
        else:
            st.info("Please log in to access the tool.")

    # --- Content Routing ---

    if not st.session_state.is_authenticated:
        login_page(auth_service)
    
    elif st.session_state.current_page == "Dashboard":
        dashboard_page(db_manager)
        
    elif st.session_state.current_page == "Project Management":
        projects_page(db_manager)

    elif st.session_state.current_page == "Kanban Board":
        kanban_page(db_manager)
        
    elif st.session_state.current_page == "Sprint Management":
        sprint_page(db_manager)
        
    elif st.session_state.current_page == "Gantt & WBS":
        gantt_page(db_manager)
        
    elif st.session_state.current_page == "Risk Register":
        risk_register_page(db_manager)

    elif st.session_state.current_page == "Reports & Analytics":
        reports_page(db_manager)

    elif st.session_state.current_page == "Administration":
        administration_page(db_manager)


    # --- Footer ---
    st.markdown("""
    <style>
        .footer {
            position: fixed;
            left: 0;
            bottom: 0;
            width: 100%;
            background-color: #f0f2f6;
            color: #555;
            text-align: center;
            padding: 10px;
            font-size: 0.8rem;
            z-index: 100;
            border-top: 1px solid #ddd;
        }
    </style>
    <div class="footer">
        Project Management Tool Developed by Mansoor Sarookh, CS Student at GPGC Swabi
    </div>
    """, unsafe_allow_html=True)

if __name__ == '__main__':
    main_app()
