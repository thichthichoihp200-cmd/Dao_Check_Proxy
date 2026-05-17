import requests
import threading
import queue
import os
import sys
from datetime import datetime, timedelta, timezone

# Khai báo bảng màu ANSI rực rỡ (tối ưu hiển thị trên Termux Android)
C_RESET   = "\033[0m"
C_RED     = "\033[1;31m"
C_GREEN   = "\033[1;32m"
C_YELLOW  = "\033[1;33m"
C_BLUE    = "\033[1;34m"
C_MAGENTA = "\033[1;35m"
C_CYAN    = "\033[1;36m"
C_WHITE   = "\033[1;37m"

# 1. Danh sách các nguồn cung cấp proxy miễn phí (HTTP/HTTPS)
PROXY_SOURCES = [
    "https://api.proxyscrape.com/v2/?request=displayproxies&protocol=http&timeout=10000&country=all&ssl=all&anonymity=all",
    "https://www.proxy-list.download/api/v1/get?type=http",
    "https://www.proxy-list.download/api/v1/get?type=https",
    "https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/http.txt",
    "https://raw.githubusercontent.com/ShiftyTR/Proxy-List/master/http.txt",
    "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/http.txt"
]

# Danh mục quốc gia để người dùng chọn bằng số
COUNTRY_MENU = {
    "1": {"name": "Nga", "code": "RU"},
    "2": {"name": "Anh", "code": "GB"},
    "3": {"name": "Pháp", "code": "FR"},
    "4": {"name": "Mỹ", "code": "US"},
    "5": {"name": "Việt Nam", "code": "VN"},
    "6": {"name": "Trung Quốc", "code": "CN"},
    "7": {"name": "Hàn Quốc", "code": "KR"},
    "8": {"name": "Nhật Bản", "code": "JP"},
    "9": {"name": "Đức", "code": "DE"}
}

# Cấu hình hệ thống
CHECK_URL = "http://httpbin.org/ip" 
TIMEOUT = 3          # Hạ xuống 3 giây để lọc bỏ proxy chậm, tránh lỗi cảnh báo trên App
THREAD_COUNT = 50     # Số luồng check đồng thời

proxy_queue = queue.Queue()
live_proxies = []
lock = threading.Lock()

# Biến cấu hình bộ lọc do người dùng nhập
TARGET_COUNT = 0
TARGET_COUNTRY_CODE = "" 
TARGET_COUNTRY_NAME = "Tất cả"
STOP_FLAG = False  

def get_vietnam_time():
    """Lấy ngày giờ hiện tại theo múi giờ Việt Nam (UTC+7)"""
    tz_vn = timezone(timedelta(hours=7))
    return datetime.now(tz_vn).strftime("%d/%m/%Y %H:%M:%S")

def print_banner():
    """Hiển thị banner chữ TINH với hiệu ứng màu sắc rực rỡ"""
    os.system('clear' if os.name != 'nt' else 'cls')
    
    banner = f"""
{C_MAGENTA}████████╗{C_CYAN}██╗{C_YELLOW}███╗   ██╗{C_RED}██╗  ██╗
{C_MAGENTA}╚══██╔══╝{C_CYAN}██║{C_YELLOW}████╗  ██║{C_RED}██║  ██║
   {C_MAGENTA}██║   {C_CYAN}██║{C_YELLOW}██╔██╗ ██║{C_RED}███████║
   {C_MAGENTA}██║   {C_CYAN}██║{C_YELLOW}██║╚██╗██║{C_RED}██╔══██║
   {C_MAGENTA}██║   {C_CYAN}██║{C_YELLOW}██║ ╚████║{C_RED}██║  ██║
   {C_RESET}╚═╝   ╚═╝╚═╝  ╚═══╝╚═╝  ╚═╝
    """
    current_time = get_vietnam_time()
    
    print(banner)
    print(f"{C_BLUE}======================================================={C_RESET}")
    print(f"{C_WHITE}  TOOL ĐÀO & LỌC PROXY THEO QUỐC GIA - PRO VERSION{C_RESET}")
    print(f"{C_YELLOW}  Thời gian (VN): {C_CYAN}{current_time}{C_RESET}")
    print(f"{C_BLUE}======================================================={C_RESET}\n")

def fetch_proxies():
    """Tải proxy từ các nguồn về và lọc trùng"""
    print(f"{C_YELLOW}[*] Đang thu thập proxy từ các nguồn...{C_RESET}")
    raw_proxies = []
    for url in PROXY_SOURCES:
        try:
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                lines = response.text.strip().split('\n')
                for line in lines:
                    proxy = line.strip()
                    if proxy and ":" in proxy:
                        raw_proxies.append(proxy)
        except Exception:
            continue
            
    unique_proxies = list(set(raw_proxies))
    print(f"{C_GREEN}[+] Thu thập tổng cộng: {C_WHITE}{len(unique_proxies)}{C_GREEN} tổng proxy thô.{C_RESET}\n")
    return unique_proxies

def get_country_info(ip):
    """Lấy thông tin quốc gia và mã quốc gia của IP từ API"""
    try:
        response = requests.get(f"http://ip-api.com/json/{ip}", timeout=3)
        if response.status_code == 200:
            data = response.json()
            if data.get("status") == "success":
                return data.get('country', 'Unknown'), data.get('countryCode', 'Unknown')
    except Exception:
        pass
    return "Unknown", "Unknown"

def check_proxy():
    """Hàm chạy trong luồng để kiểm tra và lọc proxy"""
    global STOP_FLAG
    while not proxy_queue.empty() and not STOP_FLAG:
        proxy = proxy_queue.get()
        ip = proxy.split(":")[0]
        proxies = {
            "http": f"http://{proxy}",
            "https": f"http://{proxy}"
        }
        try:
            response = requests.get(CHECK_URL, proxies=proxies, timeout=TIMEOUT)
            if response.status_code == 200:
                country_name, country_code = get_country_info(ip)
                
                # Lọc theo quốc gia nếu người dùng chọn
                if TARGET_COUNTRY_CODE and country_code.upper() != TARGET_COUNTRY_CODE.upper():
                    proxy_queue.task_done()
                    continue
                
                with lock:
                    if STOP_FLAG:
                        proxy_queue.task_done()
                        break
                        
                    display_country = f"{country_name} [{country_code}]"
                    current_idx = len(live_proxies) + 1
                    
                    # Định dạng hiển thị rực rỡ với số thứ tự đứng đầu: [Số][LIVE]
                    print(f"{C_CYAN}[{current_idx}]{C_GREEN}[LIVE]{C_WHITE} {proxy:<22} {C_YELLOW}|{C_CYAN} Quốc gia: {display_country}{C_RESET}")
                    
                    live_proxies.append(f"{proxy} | {display_country}")
                    
                    # Lưu vào file proxy_live.txt
                    with open("proxy_live.txt", "a", encoding="utf-8") as f:
                        f.write(f"{proxy} | {display_country}\n")
                        
                    # Dừng hệ thống khi đạt đủ số lượng proxy yêu cầu
                    if TARGET_COUNT > 0 and len(live_proxies) >= TARGET_COUNT:
                        print(f"\n{C_YELLOW}[*] Đã tìm đủ số lượng {C_WHITE}{TARGET_COUNT}{C_YELLOW} proxy theo yêu cầu. Đang dừng các luồng...{C_RESET}")
                        STOP_FLAG = True
                        proxy_queue.task_done()
                        break
        except Exception:
            pass
        finally:
            proxy_queue.task_done()

def main():
    global TARGET_COUNT, TARGET_COUNTRY_CODE, TARGET_COUNTRY_NAME
    
    print_banner()
    
    # 1. Nhập số lượng mong muốn (Đổi màu chữ nhập thành màu Cyan rực rỡ)
    try:
        prompt_count = f"{C_MAGENTA}👉 {C_WHITE}Nhập số lượng proxy LIVE muốn đào (Nhập 0 hoặc Enter để lấy hết): {C_CYAN}"
        count_input = input(prompt_count).strip()
        print(C_RESET, end="") 
        TARGET_COUNT = int(count_input) if count_input else 0
    except ValueError:
        TARGET_COUNT = 0
        
    # 2. Hiển thị Menu chọn quốc gia bằng số bắt mắt
    print(f"\n                               {C_MAGENTA}--- {C_YELLOW}DANH SÁCH QUỐC GIA {C_MAGENTA}---{C_RESET}")
    menu_items = [f"{C_CYAN}{k}.{C_WHITE}{v['name']}" for k, v in COUNTRY_MENU.items()]
    print("  ".join(menu_items[0:3]))
    print("  ".join(menu_items[3:6]))
    print("  ".join(menu_items[6:9]))
    print(f"{C_CYAN}0.{C_GREEN}Chọn tất cả (ALL){C_RESET}\n")
    
    # Nhập lựa chọn quốc gia
    prompt_choice = f"{C_MAGENTA}👉 {C_WHITE}Chọn quốc gia muốn đào (Nhập số từ 0-9): {C_CYAN}"
    choice = input(prompt_choice).strip()
    print(C_RESET, end="") 
    
    if choice in COUNTRY_MENU:
        TARGET_COUNTRY_CODE = COUNTRY_MENU[choice]["code"]
        TARGET_COUNTRY_NAME = COUNTRY_MENU[choice]["name"]
    else:
        TARGET_COUNTRY_CODE = "" 
        TARGET_COUNTRY_NAME = "Tất cả"

    print(f"\n{C_BLUE}======================================================={C_RESET}\n")

    # Xóa file kết quả cũ nếu tồn tại trước đó
    if os.path.exists("proxy_live.txt"):
        os.remove("proxy_live.txt")
        
    # Tiến hành đào và check luồng
    proxies = fetch_proxies()
    
    for proxy in proxies:
        proxy_queue.put(proxy)
        
    limit_info = f"{TARGET_COUNT}" if TARGET_COUNT > 0 else "Không giới hạn"
    
    print(f"{C_YELLOW}[*] Cấu hình chạy: Quốc gia: {C_CYAN}{TARGET_COUNTRY_NAME}{C_YELLOW} | Giới hạn: {C_CYAN}{limit_info}{C_RESET}")
    print(f"{C_YELLOW}[*] Đang quét với {C_CYAN}{THREAD_COUNT}{C_YELLOW} luồng...{C_RESET}\n")
    
    # Khởi chạy đa luồng (Multi-threading)
    threads = []
    for _ in range(THREAD_COUNT):
        t = threading.Thread(target=check_proxy)
        t.daemon = True
        t.start()
        threads.append(t)
        
    # Vòng lặp chờ hàng đợi giải phóng hoặc cờ dừng kích hoạt
    while not proxy_queue.empty():
        if STOP_FLAG:
            break
            
    # Dọn dẹp hàng đợi còn thừa an toàn
    with proxy_queue.mutex:
        proxy_queue.queue.clear()
        
    print(f"\n{C_MAGENTA}--- HOÀN THÀNH ---{C_RESET}")
    print(f"{C_GREEN}[+] Tổng số proxy hợp lệ đã lưu tại 'proxy_live.txt': {C_WHITE}{len(live_proxies)}{C_RESET}")

if __name__ == "__main__":
    main()
