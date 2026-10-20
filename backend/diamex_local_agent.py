import json
import mimetypes
import os
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn
from configparser import ConfigParser

import requests
import import_diamex_portable as portable
from io import BytesIO

try:
    from PIL import Image
except ImportError:
    Image = None

DEFAULT_HOST = '127.0.0.1'
DEFAULT_PORT = 8765
DEFAULT_ALLOWED_ORIGINS = [
    'https://www.hydria.mg',
    'https://hydria.mg',
    'https://compta.hydria.mg',
    'http://localhost:8000',
]
DEFAULT_SCAN_BATCH_SIZE = 5
DEFAULT_SCAN_BATCH_RETRIES = 2
AGENT_SCAN_BATCH_SIZE = DEFAULT_SCAN_BATCH_SIZE
AGENT_SCAN_BATCH_RETRIES = DEFAULT_SCAN_BATCH_RETRIES
IMPORT_JOBS = {}
IMPORT_JOBS_LOCK = threading.Lock()


def load_agent_config():
    config = ConfigParser()
    config_file = 'config_import.ini'
    if os.path.exists(config_file):
        config.read(config_file, encoding='utf-8')

    host = config.get('AGENT', 'HOST', fallback=DEFAULT_HOST)
    port = config.getint('AGENT', 'PORT', fallback=DEFAULT_PORT)
    origins_raw = config.get('AGENT', 'ALLOWED_ORIGINS', fallback=', '.join(DEFAULT_ALLOWED_ORIGINS))
    allowed_origins = [o.strip().rstrip('/') for o in origins_raw.split(',') if o.strip()]
    scan_batch_size = config.getint('AGENT', 'SCAN_BATCH_SIZE', fallback=DEFAULT_SCAN_BATCH_SIZE)
    scan_batch_retries = config.getint('AGENT', 'SCAN_BATCH_RETRIES', fallback=DEFAULT_SCAN_BATCH_RETRIES)

    return host, port, allowed_origins, scan_batch_size, scan_batch_retries


def _sanitize_scan_batch_size(scan_batch_size):
    try:
        value = int(scan_batch_size)
    except (TypeError, ValueError):
        value = DEFAULT_SCAN_BATCH_SIZE
    return max(1, min(value, 20))


def _sanitize_scan_batch_retries(scan_batch_retries):
    try:
        value = int(scan_batch_retries)
    except (TypeError, ValueError):
        value = DEFAULT_SCAN_BATCH_RETRIES
    return max(0, min(value, 5))


def _is_allowed_origin(origin, allowed_origins):
    origin = (origin or '').strip().rstrip('/')
    if not origin:
        return False

    allowed_set = {
        str(item or '').strip().rstrip('/')
        for item in (allowed_origins or [])
        if str(item or '').strip()
    }
    if origin in allowed_set:
        return True

    if origin.startswith('https://'):
        host = origin[len('https://'):]
        if host == 'hydria.mg' or host.endswith('.hydria.mg'):
            return True

    if origin.startswith('http://'):
        host = origin[len('http://'):]
        if host.startswith('localhost') or host.startswith('127.0.0.1'):
            return True

    return False


def _safe_emit_progress(callback, event_type, **kwargs):
    if not callback:
        return

    payload = {'type': event_type}
    payload.update(kwargs)
    try:
        callback(payload)
    except Exception:
        return


def _make_job_event(event_type, **kwargs):
    payload = {'type': event_type, 'timestamp': time.time()}
    payload.update(kwargs)
    return payload


def init_import_job(job_id, total_files=0, import_scans=False):
    with IMPORT_JOBS_LOCK:
        IMPORT_JOBS[job_id] = {
            'job_id': job_id,
            'status': 'running',
            'started_at': time.time(),
            'updated_at': time.time(),
            'total_files': total_files,
            'import_scans': import_scans,
            'events': [],
            'result': None,
            'error': '',
        }


def append_import_job_event(job_id, event_type, **kwargs):
    event = _make_job_event(event_type, **kwargs)
    with IMPORT_JOBS_LOCK:
        job = IMPORT_JOBS.get(job_id)
        if not job:
            return
        job['updated_at'] = time.time()
        if event_type == 'start':
            job['total_files'] = event.get('total_files') or job.get('total_files') or 0
            job['import_scans'] = bool(event.get('import_scans'))
        job['events'].append(event)
        if len(job['events']) > 500:
            job['events'] = job['events'][-500:]


def complete_import_job(job_id, success, result=None, error=''):
    with IMPORT_JOBS_LOCK:
        job = IMPORT_JOBS.get(job_id)
        if not job:
            return
        job['status'] = 'done'
        job['updated_at'] = time.time()
        job['result'] = result
        job['error'] = error or ''
        if result is not None:
            job['events'].append(_make_job_event('done', success=success, results=result.get('results', []), error=error or ''))
            if len(job['events']) > 500:
                job['events'] = job['events'][-500:]


def fail_import_job(job_id, error):
    with IMPORT_JOBS_LOCK:
        job = IMPORT_JOBS.get(job_id)
        if not job:
            return
        job['status'] = 'done'
        job['updated_at'] = time.time()
        job['error'] = error or 'Erreur inconnue'
        job['events'].append(_make_job_event('done', success=False, results=[], error=job['error']))
        if len(job['events']) > 500:
            job['events'] = job['events'][-500:]


def get_import_job_payload(job_id, after_index=0):
    with IMPORT_JOBS_LOCK:
        job = IMPORT_JOBS.get(job_id)
        if not job:
            return None
        after_index = max(0, int(after_index or 0))
        events = job['events'][after_index:]
        result = job['result']
        payload = {
            'ok': True,
            'job_id': job_id,
            'status': job['status'],
            'total_files': job.get('total_files', 0),
            'import_scans': bool(job.get('import_scans')),
            'started_at': job.get('started_at'),
            'updated_at': job.get('updated_at'),
            'error': job.get('error', ''),
            'events': events,
            'next_index': after_index + len(events),
            'done': job['status'] == 'done',
        }
        if result is not None:
            payload['result'] = result
        return payload


def send_to_django(file_path, fichier_nom, data, employe_surnom, selected_months=None):
    batch_size = portable._sanitize_import_batch_size(portable.IMPORT_BATCH_SIZE)
    data_rows = list(data.get('data_rows') or [])
    soldes_rows = list(data.get('soldes_rows') or [])
    chunk_count = max(1, (len(data_rows) + batch_size - 1) // batch_size)
    all_entry_keys = [
        {'prog': row.get('Prog'), 'id_access': row.get('ID')}
        for row in data_rows
        if row.get('ID') is not None
    ]
    last_payload = {}

    for chunk_index, start in enumerate(range(0, len(data_rows) or 1, batch_size), start=1):
        data_chunk = data_rows[start:start + batch_size] if data_rows else []
        soldes_chunk = soldes_rows if chunk_index == 1 else []
        post_data = {
            'file_path': file_path,
            'fichier_nom': fichier_nom,
            'data_rows': json.dumps(data_chunk),
            'soldes_rows': json.dumps(soldes_chunk),
            'employe_surnom': employe_surnom,
            'chunk_index': str(chunk_index),
            'chunk_count': str(chunk_count),
            'selected_months': ','.join(selected_months or []),
        }
        if chunk_index == chunk_count:
            post_data['all_entry_keys'] = json.dumps(all_entry_keys)

        response = requests.post(
            f"{portable.DJANGO_URL}/comptabilite/api/import-from-access/",
            data=post_data,
            headers=portable.AUTH_HEADERS,
            timeout=portable.TIMEOUT,
        )

        result = {
            'status_code': response.status_code,
            'text': response.text[:1000],
            'success': False,
            'chunk_index': chunk_index,
            'chunk_count': chunk_count,
        }

        if response.status_code != 200:
            result['error'] = f"HTTP {response.status_code}"
            return result

        try:
            payload = response.json()
            result.update(payload)
        except ValueError:
            result['error'] = 'Invalid JSON response from Django'
            return result

        result['success'] = bool(result.get('success'))
        if not result['success']:
            return result
        last_payload = result

    return last_payload or {
        'status_code': 200,
        'text': '',
        'success': True,
        'chunk_index': 1,
        'chunk_count': 1,
    }


def _normalize_scan_value(scan_value):
    scan_clean = (scan_value or '').strip().strip('#')
    if not scan_clean:
        return ''
    if scan_clean.startswith('./') or scan_clean.startswith('.\\'):
        return scan_clean[2:]
    return scan_clean.lstrip('.')


def _resolve_scan_path(file_path, scan_value):
    scan_clean = (scan_value or '').strip().strip('#')
    if not scan_clean:
        return ''

    is_absolute = (
        (len(scan_clean) > 2 and scan_clean[1] == ':' and scan_clean[2] in ('\\', '/')) or
        scan_clean.startswith('\\\\') or
        scan_clean.startswith('/')
    )
    if is_absolute:
        return os.path.normpath(scan_clean)

    base_dir = os.path.dirname(file_path or '')
    scan_rel = _normalize_scan_value(scan_clean)
    if not base_dir:
        return os.path.normpath(scan_rel)
    return os.path.normpath(os.path.join(base_dir, scan_rel.lstrip('\\/')))


def _prepare_scan_upload_payload(local_path, id_access):
    extension = os.path.splitext(local_path)[1].lower()
    content_type = mimetypes.guess_type(local_path)[0] or 'application/octet-stream'

    if extension in ('.tif', '.tiff') and Image is not None:
        with open(local_path, 'rb') as source_file:
            content = source_file.read()

        with Image.open(BytesIO(content)) as img:
            frames = []
            total_pages = getattr(img, 'n_frames', 1) or 1
            for page_index in range(total_pages):
                img.seek(page_index)
                frame = img.copy()
                if frame.mode not in ('RGB', 'L'):
                    frame = frame.convert('RGB')
                frames.append(frame)

        pdf_buffer = BytesIO()
        first_frame, *other_frames = frames
        first_frame.save(pdf_buffer, format='PDF', save_all=True, append_images=other_frames)
        pdf_buffer.seek(0)

        filename = f"{id_access}.pdf"
        return pdf_buffer.read(), filename, 'application/pdf', True

    with open(local_path, 'rb') as source_file:
        content = source_file.read()

    filename = f"{id_access}{extension or '.bin'}"
    return content, filename, content_type, False


def _build_temp_pdf_for_tiff(file_path):
    if Image is None:
        return file_path

    normalized_path = os.path.normpath(file_path)
    temp_dir = os.path.join(tempfile.gettempdir(), 'hydria_diamex_agent_pdf')
    os.makedirs(temp_dir, exist_ok=True)

    base_name = os.path.splitext(os.path.basename(normalized_path))[0]
    pdf_path = os.path.join(temp_dir, f"{base_name}.pdf")

    try:
        source_mtime = os.path.getmtime(normalized_path)
        if os.path.exists(pdf_path) and os.path.getmtime(pdf_path) >= source_mtime:
            return pdf_path
    except OSError:
        pass

    with Image.open(normalized_path) as img:
        frames = []
        total_pages = getattr(img, 'n_frames', 1) or 1
        for page_index in range(total_pages):
            img.seek(page_index)
            frame = img.copy()
            if frame.mode not in ('RGB', 'L'):
                frame = frame.convert('RGB')
            frames.append(frame)

    first_frame, *other_frames = frames
    first_frame.save(pdf_path, format='PDF', save_all=True, append_images=other_frames)
    return pdf_path


def fetch_existing_imported_scan_ids(fichier_nom, targets, progress_callback=None):
    existing_ids = set()
    batch_size = 200
    batch_count = max(1, (len(targets) + batch_size - 1) // batch_size)

    for start in range(0, len(targets), batch_size):
        batch = targets[start:start + batch_size]
        batch_index = (start // batch_size) + 1
        _safe_emit_progress(
            progress_callback,
            'scan_check_existing',
            checked=min(start + len(batch), len(targets)),
            total_candidates=len(targets),
            batch_index=batch_index,
            batch_count=batch_count,
        )
        payload = {
            'fichier_nom': fichier_nom,
            'entries': [
                {
                    'id_access': target['id_access'],
                    'scan_value': target['scan_value'],
                    'local_extension': target.get('local_extension') or '',
                }
                for target in batch
            ],
        }

        try:
            response = requests.post(
                f"{portable.SCAN_API_URL}/comptabilite/api/imported-scans-status/",
                json=payload,
                headers=portable.AUTH_HEADERS,
                timeout=min(portable.TIMEOUT, 60),
            )
            if response.status_code != 200:
                continue
            result = response.json()
            if not result.get('success'):
                continue
            existing_ids.update(int(id_access) for id_access in (result.get('existing_ids') or []))
        except Exception:
            continue

    return existing_ids


def upload_scans_to_django(
    file_path,
    fichier_nom,
    data_rows,
    progress_callback=None,
    scan_batch_size=None,
    scan_batch_retries=None,
):
    targets = []
    missing_files = 0
    converted_count = 0
    skipped_existing = 0
    errors = []
    seen_ids = set()

    for row in data_rows or []:
        id_access = row.get('ID')
        scan_value = (row.get('Scan') or '').strip()
        if not id_access or not scan_value or id_access in seen_ids:
            continue

        local_scan_path = _resolve_scan_path(file_path, scan_value)
        if not local_scan_path or not os.path.exists(local_scan_path):
            missing_files += 1
            continue

        seen_ids.add(id_access)
        targets.append({
            'id_access': id_access,
            'scan_value': scan_value,
            'local_scan_path': local_scan_path,
            'local_extension': os.path.splitext(local_scan_path)[1].lower(),
        })

    _safe_emit_progress(
        progress_callback,
        'scan_resolved',
        found_scans=len(targets),
        missing_files=missing_files,
    )

    if not targets:
        _safe_emit_progress(
            progress_callback,
            'scan_done',
            success=True,
            uploaded=0,
            total_to_upload=0,
            missing_files=missing_files,
            skipped_existing=0,
            converted=0,
            errors_count=0,
        )
        return {
            'success': True,
            'uploaded': 0,
            'missing_files': missing_files,
            'converted': 0,
            'errors': errors,
        }

    existing_ids = fetch_existing_imported_scan_ids(
        fichier_nom,
        targets,
        progress_callback=progress_callback,
    )
    if existing_ids:
        skipped_existing = len(existing_ids)
        targets = [target for target in targets if int(target['id_access']) not in existing_ids]

    _safe_emit_progress(
        progress_callback,
        'scan_plan',
        total_candidates=len(targets) + skipped_existing,
        total_to_upload=len(targets),
        skipped_existing=skipped_existing,
        missing_files=missing_files,
    )

    if not targets:
        _safe_emit_progress(
            progress_callback,
            'scan_done',
            success=True,
            uploaded=0,
            total_to_upload=0,
            missing_files=missing_files,
            skipped_existing=skipped_existing,
            converted=0,
            errors_count=0,
        )
        return {
            'success': True,
            'uploaded': 0,
            'missing_files': missing_files,
            'skipped_existing': skipped_existing,
            'converted': 0,
            'errors': errors,
        }

    uploaded_count = 0
    batch_size = _sanitize_scan_batch_size(scan_batch_size if scan_batch_size is not None else AGENT_SCAN_BATCH_SIZE)
    batch_retries = _sanitize_scan_batch_retries(
        scan_batch_retries if scan_batch_retries is not None else AGENT_SCAN_BATCH_RETRIES
    )
    all_success = True
    total_to_upload = len(targets)
    batch_count = max(1, (total_to_upload + batch_size - 1) // batch_size)

    for start in range(0, len(targets), batch_size):
        batch = targets[start:start + batch_size]
        batch_index = (start // batch_size) + 1
        payload = {
            'fichier_nom': fichier_nom,
        }
        files = {}
        metadata = []

        try:
            for index, target in enumerate(batch):
                field_name = f"scan_file_{start + index}"
                try:
                    content, upload_name, content_type, converted = _prepare_scan_upload_payload(
                        target['local_scan_path'],
                        target['id_access'],
                    )
                except Exception as exc:
                    # Fichier corrompu / vide / stub Drive non telecharge : on l'ignore
                    # sans bloquer les autres scans du lot.
                    try:
                        size = os.path.getsize(target['local_scan_path'])
                    except OSError:
                        size = -1
                    errors.append(
                        f"Scan illisible ignore (ID {target['id_access']}, {size} octets): "
                        f"{target['local_scan_path']} - {exc}"
                    )
                    continue
                if converted:
                    converted_count += 1
                metadata.append({
                    'field_name': field_name,
                    'id_access': target['id_access'],
                    'scan_value': target['scan_value'],
                    'upload_name': upload_name,
                    'local_extension': target.get('local_extension') or '',
                })
                files[field_name] = (upload_name, content, content_type)

            if not files:
                continue

            payload['scans_metadata'] = json.dumps(metadata)
            batch_success = False
            last_error = ''

            for attempt in range(1, batch_retries + 2):
                _safe_emit_progress(
                    progress_callback,
                    'scan_upload_progress',
                    batch_index=batch_index,
                    batch_count=batch_count,
                    uploaded_so_far=uploaded_count,
                    total_to_upload=total_to_upload,
                    remaining=max(total_to_upload - uploaded_count, 0),
                    converted=converted_count,
                    errors_count=len(errors),
                    stage='uploading',
                    attempt=attempt,
                    max_attempts=batch_retries + 1,
                )
                try:
                    response = requests.post(
                        f"{portable.SCAN_API_URL}/comptabilite/api/upload-imported-scans/",
                        data=payload,
                        files=files,
                        headers=portable.AUTH_HEADERS,
                        timeout=portable.TIMEOUT,
                    )

                    if response.status_code != 200:
                        last_error = f"HTTP {response.status_code} pendant l'upload des scans"
                    else:
                        result = response.json()
                        uploaded_count += int(result.get('uploaded') or 0)
                        if not result.get('success'):
                            all_success = False
                        for error in result.get('errors') or []:
                            errors.append(error)
                        batch_success = True
                        _safe_emit_progress(
                            progress_callback,
                            'scan_upload_progress',
                            batch_index=batch_index,
                            batch_count=batch_count,
                            uploaded_so_far=uploaded_count,
                            total_to_upload=total_to_upload,
                            remaining=max(total_to_upload - uploaded_count, 0),
                            converted=converted_count,
                            errors_count=len(errors),
                            stage='uploaded',
                            attempt=attempt,
                            max_attempts=batch_retries + 1,
                        )
                        break
                except Exception as exc:
                    last_error = str(exc)

                if attempt < batch_retries + 1:
                    _safe_emit_progress(
                        progress_callback,
                        'scan_upload_progress',
                        batch_index=batch_index,
                        batch_count=batch_count,
                        uploaded_so_far=uploaded_count,
                        total_to_upload=total_to_upload,
                        remaining=max(total_to_upload - uploaded_count, 0),
                        converted=converted_count,
                        errors_count=len(errors),
                        stage='retry',
                        attempt=attempt,
                        max_attempts=batch_retries + 1,
                        error=last_error,
                    )
                    # Laisser le temps au reseau de revenir apres une sortie de veille.
                    time.sleep(min(2 ** attempt, 10))

            if not batch_success:
                all_success = False
                errors.append(last_error or f"Echec lot scans {batch_index}/{batch_count}")
                _safe_emit_progress(
                    progress_callback,
                    'scan_upload_progress',
                    batch_index=batch_index,
                    batch_count=batch_count,
                    uploaded_so_far=uploaded_count,
                    total_to_upload=total_to_upload,
                    remaining=max(total_to_upload - uploaded_count, 0),
                    converted=converted_count,
                    errors_count=len(errors),
                    stage='error',
                    attempt=batch_retries + 1,
                    max_attempts=batch_retries + 1,
                    error=last_error,
                )
        except Exception as exc:
            all_success = False
            errors.append(str(exc))
            _safe_emit_progress(
                progress_callback,
                'scan_upload_progress',
                batch_index=batch_index,
                batch_count=batch_count,
                uploaded_so_far=uploaded_count,
                total_to_upload=total_to_upload,
                remaining=max(total_to_upload - uploaded_count, 0),
                converted=converted_count,
                errors_count=len(errors),
                stage='error',
                attempt=batch_retries + 1,
                max_attempts=batch_retries + 1,
                error=str(exc),
            )

    final_result = {
        'success': all_success and not errors,
        'uploaded': uploaded_count,
        'missing_files': missing_files,
        'skipped_existing': skipped_existing,
        'converted': converted_count,
        'errors': errors[:20],
    }
    _safe_emit_progress(
        progress_callback,
        'scan_done',
        success=final_result['success'],
        uploaded=uploaded_count,
        total_to_upload=total_to_upload,
        missing_files=missing_files,
        skipped_existing=skipped_existing,
        converted=converted_count,
        errors_count=len(final_result['errors']),
    )
    return final_result


def process_import_request(
    files,
    employe_surnom,
    import_scans,
    selected_months=None,
    progress_callback=None,
    scan_batch_size=None,
    scan_batch_retries=None,
):
    results = []
    all_success = True
    total_files = len(files)

    _safe_emit_progress(
        progress_callback,
        'start',
        total_files=total_files,
        import_scans=import_scans,
        selected_months=selected_months or [],
        scan_batch_size=_sanitize_scan_batch_size(scan_batch_size if scan_batch_size is not None else AGENT_SCAN_BATCH_SIZE),
        scan_batch_retries=_sanitize_scan_batch_retries(
            scan_batch_retries if scan_batch_retries is not None else AGENT_SCAN_BATCH_RETRIES
        ),
    )

    for index, item in enumerate(files, start=1):
        raw_path = item.get('path')
        file_path = raw_path
        if isinstance(file_path, str):
            file_path = file_path.strip().replace('\u00a0', ' ')
            file_path = os.path.normpath(file_path)

        fichier_nom = item.get('nom') or (os.path.basename(file_path) if file_path else 'Inconnu')
        result_entry = {
            'nom': fichier_nom,
            'path': file_path,
            'success': False,
        }

        _safe_emit_progress(
            progress_callback,
            'file_start',
            file_index=index,
            total_files=total_files,
            nom=fichier_nom,
            path=file_path,
        )

        if not file_path or not os.path.exists(file_path):
            if raw_path != file_path:
                result_entry['path_original'] = raw_path
            print(f"[NOT FOUND] {file_path!r}")
            result_entry['error'] = 'File not found'
            results.append(result_entry)
            all_success = False
            _safe_emit_progress(
                progress_callback,
                'file_done',
                file_index=index,
                total_files=total_files,
                nom=fichier_nom,
                success=False,
                error='File not found',
            )
            continue

        try:
            _safe_emit_progress(
                progress_callback,
                'file_reading',
                file_index=index,
                total_files=total_files,
                nom=fichier_nom,
            )
            data = portable.lire_access_local(file_path, selected_months=selected_months)
            _safe_emit_progress(
                progress_callback,
                'file_read',
                file_index=index,
                total_files=total_files,
                nom=fichier_nom,
                data_rows=len(data.get('data_rows') or []),
                soldes_rows=len(data.get('soldes_rows') or []),
            )

            resp = send_to_django(
                file_path,
                fichier_nom,
                data,
                employe_surnom,
                selected_months=selected_months,
            )
            result_entry.update(resp)
            _safe_emit_progress(
                progress_callback,
                'file_imported',
                file_index=index,
                total_files=total_files,
                nom=fichier_nom,
                success=bool(resp.get('success')),
                status_code=resp.get('status_code'),
                error=resp.get('text') if not resp.get('success') else '',
            )

            if resp.get('success') and import_scans:
                print(f"[SCAN] Upload scans web pour: {fichier_nom}")

                def scan_progress(event):
                    event['file_index'] = index
                    event['total_files'] = total_files
                    event['nom'] = fichier_nom
                    _safe_emit_progress(progress_callback, event.pop('type'), **event)

                scan_upload = upload_scans_to_django(
                    file_path,
                    fichier_nom,
                    data.get('data_rows') or [],
                    progress_callback=scan_progress,
                    scan_batch_size=scan_batch_size,
                    scan_batch_retries=scan_batch_retries,
                )
                result_entry['scan_upload'] = scan_upload
                print(
                    "[SCAN] Resultat {nom}: uploaded={uploaded}, skipped_existing={skipped}, "
                    "missing_files={missing}, converted={converted}, errors={errors}".format(
                        nom=fichier_nom,
                        uploaded=scan_upload.get('uploaded', 0),
                        skipped=scan_upload.get('skipped_existing', 0),
                        missing=scan_upload.get('missing_files', 0),
                        converted=scan_upload.get('converted', 0),
                        errors=len(scan_upload.get('errors') or []),
                    )
                )
                if not scan_upload.get('success'):
                    result_entry['success'] = False
                    all_success = False
            elif resp.get('success'):
                print(f"[SCAN] Upload scans web desactive pour: {fichier_nom}")
                _safe_emit_progress(
                    progress_callback,
                    'scan_skipped',
                    file_index=index,
                    total_files=total_files,
                    nom=fichier_nom,
                    reason='disabled',
                )
            elif import_scans:
                print(f"[SCAN] Upload scans web ignore pour {fichier_nom}: import compta en erreur")
                _safe_emit_progress(
                    progress_callback,
                    'scan_skipped',
                    file_index=index,
                    total_files=total_files,
                    nom=fichier_nom,
                    reason='accounting_error',
                )

            if not resp.get('success'):
                all_success = False
        except Exception as exc:
            result_entry['error'] = str(exc)
            all_success = False

        results.append(result_entry)
        _safe_emit_progress(
            progress_callback,
            'file_done',
            file_index=index,
            total_files=total_files,
            nom=fichier_nom,
            success=bool(result_entry.get('success')),
            error=result_entry.get('error', ''),
            scan_upload=result_entry.get('scan_upload'),
        )

    final_payload = {
        'ok': True,
        'success': all_success,
        'results': results,
    }
    _safe_emit_progress(
        progress_callback,
        'done',
        success=all_success,
        results=results,
    )
    return final_payload


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True
    # Sous Windows, SO_REUSEADDR peut autoriser plusieurs agents a ecouter
    # simultanement sur le meme port. Les requetes sont alors distribuees a
    # des processus differents, qui peuvent ne pas avoir le meme acces aux
    # lecteurs reseau (par exemple Google Drive G:).
    allow_reuse_address = False


class AgentHandler(BaseHTTPRequestHandler):
    server_version = 'DiameXLocalAgent/1.3'

    def _set_cors_headers(self):
        origin = self.headers.get('Origin')
        if _is_allowed_origin(origin, self.server.allowed_origins):
            self.send_header('Access-Control-Allow-Origin', origin)
            self.send_header('Vary', 'Origin')
        self.send_header('Access-Control-Allow-Methods', 'GET,POST,OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        if self.headers.get('Access-Control-Request-Private-Network') == 'true':
            self.send_header('Access-Control-Allow-Private-Network', 'true')
        
    def log_message(self, format, *args):
        # Rediriger les logs vers stdout pour que l'utilisateur les voie dans le .bat
        sys.stdout.write("%s - - [%s] %s\n" %
                         (self.address_string(),
                          self.log_date_time_string(),
                          format % args))

    def _send_json(self, status, payload):
        self.send_response(status)
        self._set_cors_headers()
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(payload).encode('utf-8'))

    def _start_stream(self):
        self.send_response(200)
        self._set_cors_headers()
        self.send_header('Content-Type', 'application/x-ndjson; charset=utf-8')
        self.send_header('Cache-Control', 'no-cache')
        self.send_header('Connection', 'close')
        self.end_headers()
        self.close_connection = True

    def _send_stream_event(self, payload):
        self.wfile.write((json.dumps(payload) + '\n').encode('utf-8'))
        self.wfile.flush()

    def _read_json_body(self):
        length = int(self.headers.get('Content-Length', '0'))
        raw = self.rfile.read(length) if length > 0 else b''
        try:
            return json.loads(raw.decode('utf-8')), None
        except ValueError:
            return None, 'Invalid JSON'

    def do_OPTIONS(self):
        self.send_response(204)
        self._set_cors_headers()
        self.end_headers()

    def do_GET(self):
        if self.path == '/health':
            self._send_json(200, {
                'ok': True,
                'version': '1.3',
                'server_url': portable.DJANGO_URL,
                'allowed_origins': self.server.allowed_origins,
            })
            return
        if self.path.startswith('/import-status/'):
            job_id = self.path.split('/import-status/', 1)[1].split('?', 1)[0].strip('/')
            after_index = 0
            if '?' in self.path:
                query = self.path.split('?', 1)[1]
                for part in query.split('&'):
                    if part.startswith('after='):
                        try:
                            after_index = int(part.split('=', 1)[1])
                        except ValueError:
                            after_index = 0
                        break
            payload = get_import_job_payload(job_id, after_index=after_index)
            if payload is None:
                self._send_json(404, {'ok': False, 'error': 'Import introuvable'})
            else:
                self._send_json(200, payload)
            return
        self._send_json(404, {'ok': False, 'error': 'Not found'})

    def do_POST(self):
        if self.path == '/open-file':
            self._handle_open_file()
            return
        if self.path == '/update-entry-access':
            self._handle_update_entry_access()
            return
        if self.path == '/export-access':
            self._handle_export_access()
            return
        if self.path == '/import-stream':
            self._handle_import_stream()
            return

        if self.path != '/import':
            self._send_json(404, {'ok': False, 'error': 'Not found'})
            return

        payload, error = self._read_json_body()
        if error:
            self._send_json(400, {'ok': False, 'error': error})
            return

        files = payload.get('files', [])
        employe_surnom = (payload.get('employe_surnom') or '').strip() or 'INCONNU'
        import_scans = bool(payload.get('import_scans'))
        selected_months = payload.get('selected_months') or []
        scan_batch_size = payload.get('scan_batch_size')
        scan_batch_retries = payload.get('scan_batch_retries')
        job_id = (payload.get('job_id') or '').strip()

        if not files:
            self._send_json(400, {'ok': False, 'error': 'No files provided'})
            return

        if job_id:
            init_import_job(job_id, total_files=len(files), import_scans=import_scans)

            def job_progress(event):
                event_type = event.pop('type')
                append_import_job_event(job_id, event_type, **event)

            try:
                result = process_import_request(
                    files,
                    employe_surnom,
                    import_scans,
                    selected_months=selected_months,
                    progress_callback=job_progress,
                    scan_batch_size=scan_batch_size,
                    scan_batch_retries=scan_batch_retries,
                )
                complete_import_job(job_id, bool(result.get('success')), result=result)
            except Exception as exc:
                fail_import_job(job_id, str(exc))
                result = {'ok': False, 'success': False, 'error': str(exc)}

            try:
                self._send_json(200 if result.get('ok') else 500, result)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                # Le navigateur peut couper la requete pendant une mise en veille.
                # Le job est deja termine et reste consultable via /import-status/.
                pass
            return

        self._send_json(
            200,
            process_import_request(
                files,
                employe_surnom,
                import_scans,
                selected_months=selected_months,
                scan_batch_size=scan_batch_size,
                scan_batch_retries=scan_batch_retries,
            )
        )

    def _handle_import_stream(self):
        payload, error = self._read_json_body()
        if error:
            self._send_json(400, {'ok': False, 'error': error})
            return

        files = payload.get('files', [])
        employe_surnom = (payload.get('employe_surnom') or '').strip() or 'INCONNU'
        import_scans = bool(payload.get('import_scans'))
        selected_months = payload.get('selected_months') or []
        scan_batch_size = payload.get('scan_batch_size')
        scan_batch_retries = payload.get('scan_batch_retries')

        if not files:
            self._send_json(400, {'ok': False, 'error': 'No files provided'})
            return

        self._start_stream()
        try:
            process_import_request(
                files,
                employe_surnom,
                import_scans,
                selected_months=selected_months,
                progress_callback=self._send_stream_event,
                scan_batch_size=scan_batch_size,
                scan_batch_retries=scan_batch_retries,
            )
        except Exception as exc:
            self._send_stream_event({
                'type': 'done',
                'success': False,
                'results': [],
                'error': str(exc),
            })

    def _handle_open_file(self):
        import subprocess

        length = int(self.headers.get('Content-Length', '0'))
        raw = self.rfile.read(length) if length > 0 else b''
        try:
            payload = json.loads(raw.decode('utf-8'))
        except ValueError:
            self._send_json(400, {'ok': False, 'success': False, 'error': 'Invalid JSON'})
            return

        file_path = (payload.get('file_path') or '').strip().replace('\u00a0', ' ')
        if not file_path:
            self._send_json(400, {'ok': False, 'success': False, 'error': 'No file_path provided'})
            return

        file_path = os.path.normpath(file_path)

        if not os.path.exists(file_path):
            self._send_json(404, {'ok': False, 'success': False, 'error': f'File not found: {file_path}'})
            return

        try:
            launch_path = file_path
            if os.path.splitext(file_path)[1].lower() in ('.tif', '.tiff'):
                launch_path = _build_temp_pdf_for_tiff(file_path)

            if os.name == 'nt':
                os.startfile(launch_path)
            elif sys.platform == 'darwin':
                subprocess.Popen(['open', launch_path])
            else:
                subprocess.Popen(['xdg-open', launch_path])
        except Exception as exc:
            self._send_json(500, {'ok': False, 'success': False, 'error': str(exc)})
            return

        self._send_json(200, {'ok': True, 'success': True, 'path': launch_path})

    def _handle_export_access(self):
        import pyodbc
        from datetime import datetime

        length = int(self.headers.get('Content-Length', '0'))
        raw = self.rfile.read(length) if length > 0 else b''
        try:
            payload = json.loads(raw.decode('utf-8'))
        except ValueError:
            self._send_json(400, {'ok': False, 'success': False, 'error': 'Invalid JSON'})
            return

        file_path = (payload.get('file_path') or '').strip().replace('\u00a0', ' ')
        transactions = payload.get('transactions') or []
        if not file_path:
            self._send_json(400, {'ok': False, 'success': False, 'error': 'No file_path provided'})
            return
        if not transactions:
            self._send_json(400, {'ok': False, 'success': False, 'error': 'No transactions provided'})
            return

        file_path = os.path.normpath(file_path)
        if not os.path.exists(file_path):
            self._send_json(404, {'ok': False, 'success': False, 'error': f'File not found: {file_path}'})
            return

        try:
            conn_str = (
                r'DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};'
                f'DBQ={file_path};'
            )
            conn = pyodbc.connect(conn_str)
            cursor = conn.cursor()

            # Lire le PROG depuis la table Programme (source de verite)
            prog_base = ''
            try:
                cursor.execute("SELECT * FROM Programme")
                row = cursor.fetchone()
                prog_base = row[0] if row else ''
            except Exception:
                prog_base = ''

            rec_par_mois = {}
            results = []

            # Detecter les colonnes disponibles dans DATA pour eviter les erreurs
            data_columns = set()
            try:
                for col in cursor.columns(table='DATA'):
                    if col.column_name:
                        data_columns.add(str(col.column_name).lower())
            except Exception:
                # Fallback: on gardera la requete standard
                data_columns = set()

            candidate_fields = [
                ('Journal', lambda t, prog, date_m, date_rec, rec: t.get('journal') or ''),
                ('DateM', lambda t, prog, date_m, date_rec, rec: date_m),
                ('Rec', lambda t, prog, date_m, date_rec, rec: rec),
                ('DateRec', lambda t, prog, date_m, date_rec, rec: date_rec),
                ('Description', lambda t, prog, date_m, date_rec, rec: t.get('description') or ''),
                ('In', lambda t, prog, date_m, date_rec, rec: float(t.get('montant_in') or 0)),
                ('Out', lambda t, prog, date_m, date_rec, rec: float(t.get('montant_out') or 0)),
                ('Cat', lambda t, prog, date_m, date_rec, rec: t.get('compte') or ''),
                ('PERS', lambda t, prog, date_m, date_rec, rec: t.get('pers')),
                ('Detail', lambda t, prog, date_m, date_rec, rec: t.get('detail') or ''),
                ('Info', lambda t, prog, date_m, date_rec, rec: t.get('info') or ''),
                ('Fin', lambda t, prog, date_m, date_rec, rec: t.get('fin') or ''),
                ('Scan', lambda t, prog, date_m, date_rec, rec: t.get('scan') or ''),
                ('Prog', lambda t, prog, date_m, date_rec, rec: prog),
                ('ACTIV', lambda t, prog, date_m, date_rec, rec: t.get('activ')),
                ('fournisseur', lambda t, prog, date_m, date_rec, rec: t.get('fournisseur')),
            ]

            for t in transactions:
                tx_id = t.get('transaction_id')
                try:
                    date_rec_iso = t.get('date_rec')
                    date_rec_str = None
                    date_m_str = None
                    mois_key = None
                    if date_rec_iso:
                        dt = datetime.fromisoformat(date_rec_iso)
                        date_rec_str = dt.strftime('%d/%m/%Y')
                        date_m_str = dt.replace(day=1).strftime('%d/%m/%Y')
                        mois_key = dt.strftime('%Y-%m')

                    if mois_key:
                        if mois_key not in rec_par_mois:
                            cursor.execute("SELECT MAX(Rec) FROM DATA WHERE FORMAT(DateM, 'yyyy-mm') = ?", (mois_key,))
                            max_rec_row = cursor.fetchone()
                            rec_par_mois[mois_key] = max_rec_row[0] if max_rec_row and max_rec_row[0] else 0
                        rec_par_mois[mois_key] += 1
                        rec = rec_par_mois[mois_key]
                    else:
                        rec = 1

                    # Construire une requete d'insert dynamique selon les colonnes disponibles
                    selected_fields = []
                    values = []
                    for field, getter in candidate_fields:
                        if not data_columns or field.lower() in data_columns:
                            selected_fields.append(field)
                            values.append(getter(t, prog_base, date_m_str, date_rec_str, rec))

                    sql_fields = ', '.join([f'[{f}]' if f in ('In', 'Out') else f for f in selected_fields])
                    sql_placeholders = ', '.join(['?'] * len(selected_fields))
                    sql = f"INSERT INTO DATA ({sql_fields}) VALUES ({sql_placeholders})"
                    cursor.execute(sql, tuple(values))
                    cursor.execute("SELECT @@IDENTITY")
                    access_id = cursor.fetchone()[0]
                    results.append({
                        'transaction_id': tx_id,
                        'access_id': int(access_id),
                        'success': True
                    })
                except Exception as exc:
                    results.append({
                        'transaction_id': tx_id,
                        'success': False,
                        'error': str(exc)
                    })

            conn.commit()
            cursor.close()
            conn.close()

            inserted = len([r for r in results if r.get('success')])
            failed = [r for r in results if not r.get('success')]
            error = None
            if inserted == 0:
                if failed:
                    error = failed[0].get('error') or 'Aucune ligne inseree'
                else:
                    error = 'Aucune ligne inseree'
            self._send_json(200, {
                'ok': True,
                'success': inserted > 0,
                'inserted': inserted,
                'prog': prog_base,
                'results': results,
                'error': error
            })
        except Exception as exc:
            self._send_json(500, {'ok': False, 'success': False, 'error': str(exc)})

    def _handle_update_entry_access(self):
        import pyodbc

        length = int(self.headers.get('Content-Length', '0'))
        raw = self.rfile.read(length) if length > 0 else b''
        try:
            payload = json.loads(raw.decode('utf-8'))
        except ValueError:
            self._send_json(400, {'ok': False, 'success': False, 'error': 'Invalid JSON'})
            return

        file_path = (payload.get('file_path') or '').strip().replace('\u00a0', ' ')
        id_access = payload.get('id_access')
        updates = payload.get('updates') or {}

        if not file_path:
            self._send_json(400, {'ok': False, 'success': False, 'error': 'No file_path provided'})
            return
        if not id_access:
            self._send_json(400, {'ok': False, 'success': False, 'error': 'No id_access provided'})
            return
        if not updates:
            self._send_json(200, {'ok': True, 'success': True, 'message': 'Aucune modification Access a appliquer'})
            return

        file_path = os.path.normpath(file_path)
        if not os.path.exists(file_path):
            self._send_json(404, {'ok': False, 'success': False, 'error': f'File not found: {file_path}'})
            return

        allowed_fields = {'Description', 'Info', 'Detail', 'Cat', 'Fournisseur'}
        safe_updates = {k: v for k, v in updates.items() if k in allowed_fields}
        if not safe_updates:
            self._send_json(400, {'ok': False, 'success': False, 'error': 'No valid fields to update'})
            return

        try:
            conn_str = (
                r'DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};'
                f'DBQ={file_path};'
            )
            conn = pyodbc.connect(conn_str)
            cursor = conn.cursor()

            sets = []
            params = []
            for field, value in safe_updates.items():
                sets.append(f"{field}=?")
                params.append(value)
            params.append(id_access)
            sql = f"UPDATE DATA SET {', '.join(sets)} WHERE ID=?"
            cursor.execute(sql, tuple(params))
            conn.commit()

            rowcount = cursor.rowcount
            cursor.close()
            conn.close()

            self._send_json(200, {
                'ok': True,
                'success': True,
                'updated': int(rowcount) if rowcount is not None else 0
            })
        except Exception as exc:
            self._send_json(500, {'ok': False, 'success': False, 'error': str(exc)})


def main():
    host, port, allowed_origins, scan_batch_size, scan_batch_retries = load_agent_config()
    global AGENT_SCAN_BATCH_SIZE, AGENT_SCAN_BATCH_RETRIES
    AGENT_SCAN_BATCH_SIZE = _sanitize_scan_batch_size(scan_batch_size)
    AGENT_SCAN_BATCH_RETRIES = _sanitize_scan_batch_retries(scan_batch_retries)

    server = ThreadedHTTPServer((host, port), AgentHandler)
    server.allowed_origins = allowed_origins

    print('DiameX Local Agent running')
    print(f'Listening on http://{host}:{port}')
    print(f'Django server: {portable.DJANGO_URL}')
    print(f'Scan batches: {AGENT_SCAN_BATCH_SIZE} file(s) per request, retries={AGENT_SCAN_BATCH_RETRIES}')
    print('Allowed origins:')
    for origin in allowed_origins:
        print(f'  - {origin}')

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('Shutting down...')
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
