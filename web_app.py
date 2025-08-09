from quart import Quart, request, redirect, url_for, jsonify, Response, g, abort, render_template, flash
from controller.GeoController import GeoController
from controller.UserController import UserController
from functools import wraps
import jwt
from dotenv import load_dotenv  
import os  
from datetime import datetime, timedelta, timezone

load_dotenv()
app = Quart(__name__)
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0  # disable caching

# SECRET_KEY wird aus der .env-Datei geladen
app.secret_key = os.getenv('SECRET_KEY')  

controller = GeoController()
user_controller = UserController()

def token_required(*roles):
    def decorator(f):
        @wraps(f)
        async def decorated_function(*args, **kwargs):
            if not g.get('user', {}).get('is_authenticated', False):
                abort(401, description="Token is missing or invalid!")
            if roles and g.user['role'] not in roles:
                abort(403, description="You do not have access to this resource")
            return await f(*args, **kwargs)
        return decorated_function
    return decorator

def load_user_from_request():
    token = request.cookies.get('auth_token') or request.headers.get('Authorization')
    if token:
        try:
            data = jwt.decode(token, app.secret_key, algorithms=["HS256"])
            g.user = {'id': data['sub'], 'role': data['role'], 'is_authenticated': True}

            token_exp = datetime.fromtimestamp(data['exp'], timezone.utc)
            current_time = datetime.now(timezone.utc)
            
            remaining_time = token_exp - current_time
            if remaining_time < timedelta(minutes=5):
                new_token = jwt.encode({
                    'sub': g.user['id'],
                    'role': g.user['role'],
                    'exp': (datetime.now(timezone.utc) + timedelta(minutes=60)).timestamp()
                }, app.secret_key, algorithm='HS256')

                g.new_token = new_token

        except jwt.ExpiredSignatureError:
            g.user = {'is_authenticated': False}
        except jwt.InvalidTokenError:
            g.user = {'is_authenticated': False}
    else:
        g.user = {'is_authenticated': False}

@app.route("/")
async def default():
    return redirect(url_for('login'))

@app.route('/show_cookies')
async def show_cookies():
    cookies = request.cookies
    return f"Alle Cookies: {cookies}"

@app.route('/add_user', methods=['POST'])
@token_required('admin')
async def add_user():
    data = await request.form
    return await user_controller.create_user(data['username'], data['password'], data.get('role', 'user'))

@app.route('/edit_user/<int:user_id>', methods=['POST'])
@token_required('admin')
async def edit_user(user_id):
    data = await request.form
    return await user_controller.update_user(user_id, data['username'], data['password'], data['role'])

@app.route('/delete_user/<int:user_id>', methods=['POST'])
@token_required('admin')
async def delete_user(user_id):
    return await user_controller.delete_user(user_id)

@app.route('/login', methods=['GET'])
async def login():
    return await user_controller.get_login()

@app.route('/login', methods=['POST'])
async def login_post():
    return await user_controller.post_login()

@app.route('/logout')
async def logout():
    return await user_controller.logout()

@app.route("/export_history")
@token_required('user', 'datamanager', 'admin')
async def export_history():
    return await user_controller.get_export_history(g.user['id'])

@app.route("/manage_users")
@token_required('admin')
async def manage_users():
    return await user_controller.manage_users()


@app.before_serving
async def before_serving():
    await controller.ensure_connection()
    await controller.create_tables()
    await user_controller.create_admin_user()

@app.before_request
def before_request():
    load_user_from_request()

@app.after_request
async def add_cache_control_headers(response: Response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

@app.route("/information")
#@token_required('user', 'datamanager', 'admin')
async def information():
    return await controller.information()

@app.route("/export", methods=['GET'])
async def export():
    return await controller.export_page()

@app.route("/export_csv", methods=['GET', 'POST'])
async def export_csv():
    return await controller.export_csv(request)

@app.route("/generate_boxplot", methods=['POST'])
#@token_required('user', 'datamanager', 'admin')
async def generate_boxplot():
    return await controller.generate_boxplot(request)

@app.route("/platform", methods=['GET'])
#@token_required('user', 'datamanager', 'admin')
async def platform():
    return await controller.platform()

@app.route("/platform/<gpl_id>", methods=['GET'])
#@token_required('user', 'datamanager', 'admin')
async def platform_details(gpl_id):
    return await controller.platform_details(gpl_id=gpl_id)

@app.route("/series/<gse_id>", methods=['GET'])
#@token_required('user', 'datamanager', 'admin')
async def series_details(gse_id):
    return await controller.get_series_details_w_gsms(gse_id)

@app.route("/sample/<gsm_id>", methods=['GET'])
#@token_required('user', 'datamanager', 'admin')
async def gsm_details(gsm_id):
    return await controller.get_gsm_details_by_id(gsm_id)

@app.route('/series_import', methods=['GET'])
@token_required('datamanager', 'admin')
async def series_import_get():
    return await controller.series_import_get()

@app.route('/series_import', methods=['POST'])
@token_required('datamanager', 'admin')
async def series_import_post():
    return await controller.series_import_post(request)

@app.route("/import/<gse_id>", methods=['GET'])
@token_required('datamanager', 'admin')
async def import_samples_page(gse_id):
    return await controller.import_samples_page(gse_id)

@app.route("/import_samples", methods=['POST'])
@token_required('datamanager', 'admin')
async def import_samples():
    form = await request.form
    gse_id = form.get('gse_id')
    sample_ids = form.getlist('sample_ids[]')
    import_id = form.get('import_id')
    filter_p_value = form.get('filter_p_value') == True 

    return await controller.start_import(gse_id, sample_ids, import_id, filter_p_value)


@app.route('/status/<import_id>', methods=['GET'])
@token_required('datamanager', 'admin')
async def import_status(import_id):
    status = await controller.get_import_status(import_id)
    print("call of import_id: ", import_id)
    return jsonify(status)

#======== edit series =================

@app.route('/edit_series/<gse_id>', methods=['GET'])
@token_required('datamanager', 'admin')
async def edit_series_page(gse_id):
    return await controller.edit_series_page(gse_id)

@app.route('/add_group', methods=['POST'])
@token_required('datamanager', 'admin')
async def add_group():
    form = await request.form
    name = form.get('name')
    short_name = form.get('short_name')
    gse_id = form.get('gse_id')

    result = await controller.add_group(name, short_name)

    if result["status"] == "error":
        await flash(result["message"], 'danger')  

    return redirect(url_for('edit_series_page', gse_id=gse_id))


@app.route('/remove_group', methods=['POST'])
@token_required('datamanager', 'admin')
async def remove_group():
    form = await request.form
    group_id = form.get('group_id')
    gse_id = form.get('gse_id')
    await controller.remove_group(group_id)
    return redirect(url_for('edit_series_page', gse_id=gse_id))

@app.route('/assign_sample_to_group', methods=['POST'])
@token_required('datamanager', 'admin')
async def assign_sample_to_group():
    form = await request.form
    sample_id = form.get('sample_id')
    group_id = form.get('group_id')
    gse_id = form.get('gse_id')

    group_id = None if group_id == "" else group_id

    await controller.assign_sample_to_group(sample_id, group_id)
    return jsonify({"status": "success"})

@app.route('/update_bto', methods=['POST'])
@token_required('datamanager', 'admin')
async def update_bto():
    form = await request.form
    gse_id = form.get('gse_id')
    bto_id = form.get('bto_id')
    await controller.update_bto(gse_id, bto_id)
    return redirect(url_for('edit_series_page', gse_id=gse_id))

@app.route('/update_series_status', methods=['POST'])
@token_required('datamanager', 'admin')
async def update_series_status():
    data = await request.get_json()  
    gse_id = data.get('gse_id')
    is_finished = bool(data.get('is_finished'))
    print("das sind die variablen", gse_id, is_finished)  
    await controller.update_series_status(gse_id, is_finished)
    return redirect(url_for('edit_series_page', gse_id=gse_id))

#======== New route to fetch tissue types =================
@app.route('/fetch_bto/<bto_id>')
@token_required('datamanager', 'admin')
async def fetch_bto_handler(bto_id):
    response = await controller.fetch_bto_details(bto_id)
    return jsonify(response)

@app.route('/update_tissue_type_series', methods=['POST'])
@token_required('datamanager', 'admin')
async def update_tissue_type_series():
    form = await request.form
    gse_id = form.get('gse_id')
    tissue_type = form.get('tissue_type')
    await controller.update_tissue_type_series(gse_id, tissue_type)
    return redirect(url_for('edit_series_page', gse_id=gse_id))

#======== API export endpoint =================
@app.route("/api/export", methods=['POST'])
async def api_export():
    return await controller.api_export(request)

@app.route('/add_tissue_type', methods=['POST'])
@token_required('datamanager', 'admin')
async def add_tissue_type():
    form = await request.form
    name = form.get('name')
    gse_id = form.get('gse_id')
    
    # Call the add_tissue_type method and get result
    result = await controller.add_tissue_type(name)
    
    # Check result status and flash message accordingly
    if result["status"] == "error":
        await flash(result["message"], 'danger')
    else:
        await flash(result["message"], 'success')
    
    return redirect(url_for('edit_series_page', gse_id=gse_id))


@app.route('/remove_tissue_type', methods=['POST'])
@token_required('admin') 
async def remove_tissue_type():
    form = await request.form
    tissue_type_id = form.get('tissue_type_id')
    gse_id = form.get('gse_id')
    
    await controller.remove_tissue_type(tissue_type_id)  
    await flash('Tissue type deleted successfully.', 'success')  
    return redirect(url_for('edit_series_page', gse_id=gse_id))


@app.route('/assign_sample_tissue_type', methods=['POST'])
@token_required('datamanager', 'admin')
async def assign_sample_tissue_type():
    form = await request.form
    sample_id = form.get('sample_id')
    tissue_type_id = form.get('tissue_type_id')
    gse_id = form.get('gse_id')

    tissue_type_id = None if tissue_type_id == "" else tissue_type_id

    await controller.assign_sample_tissue_type(sample_id, tissue_type_id)
    return jsonify({"status": "success"})


if __name__ == "__main__":
    app.run(debug=True)
