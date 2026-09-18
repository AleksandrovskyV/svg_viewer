# svg_viewer/server.py

# создёт локальный сервер с вшитым html в качестве интерфейса
# для просмотра всех файлов заданного типа в выбранной директории
# включая подпапки * нужен был мне для svg типа файлов

import os, sys, json, re
from pathlib import Path
import http.server as pyserver
import socketserver, webbrowser
import subprocess
import mimetypes
import ctypes

TOOL_NAME = "SVG Viewer"
TOOL_DESC = "viewserver.svgviewer"
TOOL_PLAT = 0

# корень программы
if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
    ROOT = Path(sys._MEIPASS).absolute()
    SERVER_APP_DIR = Path(sys.executable).parent.absolute()
    print("pre: unpacked_to", ROOT)
else:
    ROOT = Path(__file__).parent.absolute()
    SERVER_APP_DIR = ROOT
    print("pre: root_path", ROOT)

# конфиг этого питон скрипта
_PROG_CFG = { 
    "TEMPLATE_DIR": ROOT / "core" / "template",
    "FILES_DIR": ROOT / "core" / "template" / "files",
    "TEMPLATE_CANVAS": "svg_previews_canvas.html",
    "TEMPLATE_DOM": "svg_previews_dom.html",
}

# "пользовательский" конфиг для html интерфейса
_USER_PATH = {
    "USER_SCAN_DIR": SERVER_APP_DIR, #default if package exe
    "USER_EXPORT_DIR": None,
}
#print("_PROG_CFG:", _PROG_CFG,"_USER_PATH",_USER_PATH)



# =============== GLOBAL FUNC ==================


def check_platform():
    if sys.platform == "win32":
        return 0
    elif sys.platform == "darwin": # OSX
        return 1
    elif sys.platform == "linux":  # LINUX
        return 2
    else:
        return 3


def set_app_user_model_id():
    if sys.platform == "win32":
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(f"{TOOL_DESC}")
        except Exception:
            pass

# ====== GUARD SECOND LOADS

import atexit

_lock_file_handle = None

def try_handoff(port: int) -> None:
    """Кроссплатформенная защита от повторного запуска через PID-файл."""
    global _lock_file_handle
    import tempfile

    lock_path = Path(tempfile.gettempdir()) / f"{TOOL_DESC}_{port}.lock"
    print("lockpath", lock_path)

    try:
        _lock_file_handle = open(lock_path, "w")
        
        # Пытаемся эксклюзивно заблокировать файл на уровне ОС
        if sys.platform == "win32":
            import msvcrt
            msvcrt.locking(_lock_file_handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(_lock_file_handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            
        # ЕСЛИ БЛОКИРОВКА УДАЛАСЬ — регистрируем автоудаление файла при выходе
        def cleanup():
            global _lock_file_handle
            if _lock_file_handle:
                try:
                    _lock_file_handle.close()
                    if lock_path.exists():
                        lock_path.unlink() # Физически удаляем файл с диска
                except Exception:
                    pass
        
        atexit.register(cleanup)

        # Записываем PID текущего процесса в файл
        _lock_file_handle.write(str(os.getpid()))
        _lock_file_handle.flush()
        
    except (IOError, BlockingIOError):
        # Если файл занят ДРУГИМ процессом — выходим
        if sys.platform == "win32":
            import ctypes
            user32 = ctypes.WinDLL("user32", use_last_error=True)
            user32.MessageBoxW(
                None,
                f"{TOOL_NAME} is already running.\nClose it and try again.",
                "Message",
                0x30 | 0x0 | 0x1000 | 0x00010000
            )
        else:
            print(f"\n[INFO] {TOOL_NAME} is already running. Closing this instance.")
            
        sys.exit(0)


def ask_directory(title_text="SelectFolder"):
    # 0 - tinker (crossplatform python ask)
    # 1 - classic Windows "set folder" (FolderBrowserDialog)
    # 2 - Windows Explorer for set folder (trick OpenFileDialog)
    MODE = 0
    
    if MODE == 2:
        from tkinter import filedialog, Tk

        tkwindow = Tk()
        tkwindow.withdraw()
        tkwindow.attributes('-topmost', True)

        selected_dir = filedialog.askdirectory(title=title_text)
        
        tkwindow.destroy() 
        
        if selected_dir and Path(selected_dir).exists():
            return selected_dir
        return None

    ps_script_def = f"""
    Add-Type -AssemblyName System.Windows.Forms;
    $dialog = New-Object System.Windows.Forms.FolderBrowserDialog;
    $dialog.Description = "{title_text}";
    $dialog.ShowNewFolderButton = $true;
    
    $result = $dialog.ShowDialog();
    if ($result -eq [System.Windows.Forms.DialogResult]::OK) {{
        Write-Output $dialog.SelectedPath;
    }}
    """
    
    ps_script_hack = f"""
    Add-Type -AssemblyName System.Windows.Forms;
    $dialog = New-Object System.Windows.Forms.OpenFileDialog;
    $dialog.Title = "{title_text}";
    $dialog.CheckFileExists = $false;
    $dialog.CheckPathExists = $true;
    $dialog.FileName = "Select Folder"; 
    
    $type = $dialog.GetType();
    $flagsField = $type.GetField("options", [System.Reflection.BindingFlags]::Instance -bor [System.Reflection.BindingFlags]::NonPublic);
    if ($flagsField) {{
        $flags = $flagsField.GetValue($dialog);
        $flagsField.SetValue($dialog, $flags -bor 0x00000020);
    }}
    
    $result = $dialog.ShowDialog();
    if ($result -eq [System.Windows.Forms.DialogResult]::OK) {{
        if ([System.IO.Directory]::Exists($dialog.FileName)) {{
            Write-Output $dialog.FileName;
        }} else {{
            $path = [System.IO.Path]::GetDirectoryName($dialog.FileName);
            Write-Output $path;
        }}
    }}
    """
    try:
        process = subprocess.Popen(
            ["powershell", "-NoProfile", "-Command", ps_script_def if MODE == 1 else ps_script_hack],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding='cp1251', 
            creationflags=0x08000000 
        )
        stdout, _ = process.communicate()
        
        if stdout:
            selected_path = stdout.strip()
            if selected_path and Path(selected_path).exists():
                return selected_path

    except Exception as e:
        print(f"Error folder selection: {e}")
        
    return None


# ====== NOT USING - ONLY TEST

import xml.etree.ElementTree as ET

# test calc bbox svg inside python
def calculate_svg_bbox(root_element):
    """
    Безопасный парсер геометрии. Вытаскивает числа СТРОГО из графических атрибутов (d, points, x, y, cx, cy).
    Не трогает stroke-width, версии и метаданные.
    """
    x_coords = []
    y_coords = []
    
    # Регулярка для поиска любых чисел (включая отрицательные и дробные)
    num_re = re.compile(r'[-+]?\d*\.\d+|\d+')

    # Проходим по всем элементам внутри SVG
    for elem in root_element.iter():
        tag = elem.tag.split('}')[-1] # Отрезаем namespace, если он есть
        
        # 1. Если это путь <path d="..." />
        if tag == 'path' and 'd' in elem.attrib:
            nums = [float(n) for n in num_re.findall(elem.attrib['d'])]
            x_coords.extend(nums[0::2])
            y_coords.extend(nums[1::2])
            
        # 2. Если это полигон или полилиния <polygon points="..." />
        elif tag in ['polygon', 'polyline'] and 'points' in elem.attrib:
            nums = [float(n) for n in num_re.findall(elem.attrib['points'])]
            x_coords.extend(nums[0::2])
            y_coords.extend(nums[1::2])
            
        # 3. Если это базовые фигуры (rect, circle, ellipse, line)
        elif tag == 'rect':
            x = float(elem.attrib.get('x', 0))
            y = float(elem.attrib.get('y', 0))
            w = float(elem.attrib.get('width', 0))
            h = float(elem.attrib.get('height', 0))
            x_coords.extend([x, x + w])
            y_coords.extend([y, y + h])
        elif tag in ['circle', 'ellipse']:
            cx = float(elem.attrib.get('cx', 0))
            cy = float(elem.attrib.get('cy', 0))
            r = float(elem.attrib.get('r', elem.attrib.get('rx', 0)))
            ry = float(elem.attrib.get('ry', r))
            x_coords.extend([cx - r, cx + r])
            y_coords.extend([cy - ry, cy + ry])
        elif tag == 'line':
            x_coords.extend([float(elem.attrib.get('x1', 0)), float(elem.attrib.get('x2', 0))])
            y_coords.extend([float(elem.attrib.get('y1', 0)), float(elem.attrib.get('y2', 0))])

    if x_coords and y_coords:
        min_x, max_x = min(x_coords), max(x_coords)
        min_y, max_y = min(y_coords), max(y_coords)
        
        w = max_x - min_x
        h = max_y - min_y
        
        if w > 0 and h > 0:
            padding = max(w, h) * 0.05 # 5% отступ безопасности
            return f"{min_x - padding} {min_y - padding} {w + padding * 2} {h + padding * 2}"
            
    return None

# test out svg from python
def inject_viewbox_and_clean(svg_text):
    """Форсирует правильный viewBox и очищает инлайновые размеры."""
    try:
        svg_pure = re.sub(r'xmlns="[^"]+"', '', svg_text, count=1)
        root = ET.fromstring(svg_pure)
        
        if root.tag == 'svg':
            root.attrib.pop('width', None)
            root.attrib.pop('height', None)
            
            current_vb = root.get('viewBox')
            if not current_vb or current_vb.strip() == "" or "NaN" in current_vb:
                calculated_vb = calculate_svg_bbox(root)
                if calculated_vb:
                    root.set('viewBox', calculated_vb)
            
            root.set('xmlns', 'http://www.w3.org/2000/svg')
            return ET.tostring(root, encoding='utf-8').decode('utf-8')
    except Exception as e:
        print(f"Ошибка парсинга файла: {e}")
    return svg_text


# =================================================

mime_db = mimetypes.MimeTypes()

class FileHandler(pyserver.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(_USER_PATH["USER_SCAN_DIR"]), **kwargs)

    def do_GET(self):
        print(f"\n[SERVER DEBUG] Входящий запрос Path: {self.path}")
        
        # 1 api route: call native windows
        if self.path.startswith('/api/set_config_path'):
            print("1 api root")
            from urllib.parse import urlparse, parse_qs
            query = parse_qs(urlparse(self.path).query)
            target_type = query.get("type", [None])[0]
            
            if target_type and target_type in ["USER_SCAN_DIR", "USER_EXPORT_DIR"]:
                print("pre2")
                title_text = "Select scan folder" if target_type == "USER_SCAN_DIR" else "Select folder export"
                
                # вызов проводника windows 10/11 для установки директории
                selected_dir = ask_directory(title_text)

                if selected_dir:
                    path_obj = Path(selected_dir).absolute()
                    _USER_PATH[target_type] = path_obj
                    
                    if target_type == "USER_SCAN_DIR":
                        self.directory = str(path_obj)
                    
                    self.send_response(200)
                    self.send_header('Content-Type', 'application/json; charset=utf-8')
                    self.end_headers()
                    self.wfile.write(json.dumps({"success": True, "path": str(path_obj)}, ensure_ascii=False).encode('utf-8'))
                    print("SUCCESS")
                    return
                else:
                    msg = "cancel folder select"
            else:
                msg = f"Error Config: {target_type}"
            
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.end_headers()
            self.wfile.write(json.dumps({"success": False, "msg": msg}, ensure_ascii=False).encode('utf-8'))
            print("debug ERROR/CANCEL:", _USER_PATH)
            return

        # 2 api route: scanning root
        if self.path == '/api/data':
            print("2 api root")
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.end_headers()
            
            files_db = []
            user_dir = _USER_PATH["USER_SCAN_DIR"] 
            tree_structure = {"name": user_dir.name, "path": "", "children": []}
            
            self.scan_directory_backend(user_dir, "", tree_structure, files_db)
            
            response_data = {
                "base_path": str(user_dir).replace("\\", "/"),
                "tree": tree_structure,
                "files": files_db
            }
            self.wfile.write(json.dumps(response_data, ensure_ascii=False).encode('utf-8'))
            return

        # 3 route - Истинные системные файлы проекта
        if self.path in ('/', '/dom') or 'files/' in self.path:
            # Главная страница
            if self.path == '/':
                file_path = _PROG_CFG["TEMPLATE_DIR"] / _PROG_CFG["TEMPLATE_CANVAS"]
                base_dir = _PROG_CFG["TEMPLATE_DIR"]
            
            # Внутренняя страница
            elif self.path == '/dom':
                file_path = _PROG_CFG["TEMPLATE_DIR"] / _PROG_CFG["TEMPLATE_DOM"]        
                base_dir = _PROG_CFG["TEMPLATE_DIR"]
            
            # Системные ассеты (запрос вида core/templates/files/...)
            elif 'files/' in self.path:
                base_dir = _PROG_CFG["FILES_DIR"]
                filename = self.path.split('/')[-1]
                file_path = base_dir / filename
                
            # Системные шаблоны (запрос вида /core/template/...)
            else:
                base_dir = _PROG_CFG["TEMPLATE_DIR"]
                filename = self.path.split('/')[-1]
                file_path = base_dir / filename
            
            # Безопасно проверяем и отдаем файл
            if file_path.exists() and file_path.is_file() and base_dir in file_path.parents:
                mime_type, _ = mime_db.guess_type(str(file_path))
                mime_type = mime_type or 'application/octet-stream'
                
                self.send_response(200)
                if "text" in mime_type or "javascript" in mime_type:
                    self.send_header('Content-Type', f'{mime_type}; charset=utf-8')
                else:
                    self.send_header('Content-Type', mime_type)
                self.end_headers()
                
                self.wfile.write(file_path.read_bytes())
            else:
                self.send_response(404)
                self.end_headers()
                self.wfile.write(b"404 Not Found")
            return

        return super().do_GET()


    def scan_directory_backend(self, current_path: Path, relative_path: str, tree_node, files_db):
        try:
            for item in sorted(current_path.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
                if item.name.startswith('.'):
                    continue
                if relative_path == "" and item.name == "core" and item.is_dir():
                    continue
                
                new_rel_path = f"{relative_path}/{item.name}" if relative_path else item.name
                
                if item.is_dir():
                    child_node = {"name": item.name, "path": new_rel_path, "children": []}
                    tree_node["children"].append(child_node)
                    self.scan_directory_backend(item, new_rel_path, child_node, files_db)
                elif item.suffix.lower() == '.svg':
                    files_db.append({
                        "name": item.name,
                        "folderPath": relative_path,
                        "url": f"/{new_rel_path}" if new_rel_path else f"/{item.name}"
                    })
        except PermissionError:
            pass


if __name__ == "__main__":

    TOOL_PLAT = check_platform()
    print("platform:", TOOL_PLAT)

    if TOOL_PLAT==0:
        # 1. Регистрируем приложение в панели задач Windows
        # Сборка вторичных окон одного приложения
        set_app_user_model_id()
    
    socketserver.TCPServer.allow_reuse_address = True
    port = 8000
    httpd = None

    # Поиск свободного порта 
    # 1. Цикл занимается СТРОГО поиском свободного сетевого порта
    while int(port) < 8100:
        try:
            httpd = socketserver.TCPServer(("127.0.0.1", port), FileHandler)
            break # Порт успешно найден и забронирован, выходим из цикла
        except OSError:
            print(f"[{TOOL_NAME}][INFO] Порт {port} занят. Ищем дальше...")
            port += 1

    if not httpd:
        print(f"[{TOOL_NAME}][ERROR] Нет свободных портов в диапазоне 8000-8100.")
        sys.exit(1)

    # 2. И ТОЛЬКО ТЕПЕРЬ, когда порт железно наш, активируем защиту от дубликатов!
    try_handoff(port)

    # 3. Запуск сервера
    with httpd:
        print(f"[{TOOL_NAME}] server start at http://127.0.0.1:{port}")
        webbrowser.open(f"http://127.0.0.1:{port}")
        
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print(f"\n[{TOOL_NAME}] server Stop")
            # Насильно закрываем все сетевые потоки, чтобы сокет не зависал в TIME_WAIT
            httpd.shutdown() 
            sys.exit(0)