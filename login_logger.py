import os
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog, filedialog, scrolledtext
import html
import base64
import json
from datetime import datetime
import webbrowser
from flask import Flask, send_file
import threading
import logging

app = Flask(__name__)

class TkinterHandler(logging.Handler):
    def __init__(self, text_widget):
        super().__init__()
        self.text_widget = text_widget

    def emit(self, record):
        log_entry = self.format(record)
        self.text_widget.insert(tk.END, log_entry + '\n')
        self.text_widget.see(tk.END)

@app.route('/')
def serve_html():
    return send_file('user_info.html')

def run_flask():
    app.run(host='0.0.0.0', port=5000)

def create_or_update_html(platform, username, password, update=False):
    safe_platform = html.escape(platform)
    safe_username = html.escape(username)
    encoded_password = base64.b64encode(password.encode()).decode()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    filename = "user_info.html"
    
    if os.path.exists(filename):
        with open(filename, "r", encoding="utf-8") as file:
            content = file.read()
        
        # Extract the existing data
        data_start = content.find("var userData = ") + len("var userData = ")
        data_end = content.find("};", data_start) + 1
        user_data = json.loads(content[data_start:data_end])
        
        if safe_platform in user_data:
            if not update:
                return "update_query"
        
        user_data[safe_platform] = {
            "username": safe_username,
            "password": encoded_password,
            "timestamp": timestamp
        }
        
        # Update the content
        new_data_json = json.dumps(user_data, indent=2)
        new_content = content[:data_start] + new_data_json + content[data_end:]
    else:
        user_data = {
            safe_platform: {
                "username": safe_username,
                "password": encoded_password,
                "timestamp": timestamp
            }
        }
        new_content = f"""
<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>사용자 정보</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script>
        var userData = {json.dumps(user_data, indent=2)};

        function togglePassword(safe_platform) {{
            let passwordElement = document.getElementById('password_' + safe_platform);
            let buttonElement = document.getElementById('button_' + safe_platform);
            if (userData[safe_platform] && userData[safe_platform].password) {{
                if (passwordElement.textContent === '********') {{
                    let decodedPassword = atob(userData[safe_platform].password);
                    passwordElement.textContent = decodedPassword;
                    buttonElement.textContent = '가리기';
                }} else {{
                    passwordElement.textContent = '********';
                    buttonElement.textContent = '보기';
                }}
            }}
        }}

        function deletePlatform(safe_platform) {{
            if (confirm('정말로 이 플랫폼을 삭제하시겠습니까?')) {{
                delete userData[safe_platform];
                document.getElementById(safe_platform + '_info').remove();
            }}
        }}

        function copyToClipboard(text, buttonId) {{
            let button = document.getElementById(buttonId);
            let originalText = button.textContent;
            navigator.clipboard.writeText(text).then(() => {{
                button.textContent = '복사 성공';
                button.classList.remove('bg-gray-300', 'text-gray-700');
                button.classList.add('bg-green-500', 'text-white');
                setTimeout(() => {{
                    button.textContent = originalText;
                    button.classList.remove('bg-green-500', 'text-white');
                    button.classList.add('bg-gray-300', 'text-gray-700');
                }}, 2000);
            }}, (err) => {{
                button.textContent = '복사 실패';
                button.classList.remove('bg-gray-300', 'text-gray-700');
                button.classList.add('bg-red-500', 'text-white');
                setTimeout(() => {{
                    button.textContent = originalText;
                    button.classList.remove('bg-red-500', 'text-white');
                    button.classList.add('bg-gray-300', 'text-gray-700');
                }}, 2000);
                console.error('복사 실패: ', err);
            }});
        }}

        function renderUserData() {{
            let container = document.getElementById('user-data-container');
            container.innerHTML = '';
            for (let safe_platform in userData) {{
                let div = document.createElement('div');
                div.id = safe_platform + '_info';
                div.className = 'bg-white p-8 rounded-lg shadow-md mb-8';
                div.innerHTML = `
                    <div class="flex justify-between items-center mb-4">
                        <h2 class="text-2xl font-bold">${{safe_platform}}</h2>
                        <button onclick="deletePlatform('${{safe_platform}}')" class="px-2 py-1 bg-red-500 text-white rounded">삭제</button>
                    </div>
                    <div class="mb-4 flex items-center">
                        <p class="text-gray-700 mr-2"><span class="font-semibold">아이디:</span> ${{userData[safe_platform].username}}</p>
                        <button id="copy_username_${{safe_platform}}" onclick="copyToClipboard('${{userData[safe_platform].username}}', 'copy_username_${{safe_platform}}')" class="px-2 py-1 bg-gray-300 text-gray-700 rounded">복사</button>
                    </div>
                    <div class="mb-4 flex items-center">
                        <p class="text-gray-700 mr-2">
                            <span class="font-semibold">비밀번호:</span>
                            <span id="password_${{safe_platform}}">********</span>
                        </p>
                        <button id="button_${{safe_platform}}" onclick="togglePassword('${{safe_platform}}')" class="px-2 py-1 bg-blue-500 text-white rounded mr-2">보기</button>
                        <button id="copy_password_${{safe_platform}}" onclick="copyToClipboard(atob(userData['${{safe_platform}}'].password), 'copy_password_${{safe_platform}}')" class="px-2 py-1 bg-gray-300 text-gray-700 rounded">복사</button>
                    </div>
                    <div class="mt-2 text-sm text-gray-500">
                        <p>마지막 업데이트: ${{userData[safe_platform].timestamp}}</p>
                    </div>
                `;
                container.appendChild(div);
            }}
        }}

        window.onload = renderUserData;
    </script>
</head>
<body class="bg-gray-100 min-h-screen py-8">
    <div class="container mx-auto">
        <h1 class="text-3xl font-bold mb-8 text-center">사용자 정보</h1>
        <div id="user-data-container"></div>
    </div>
</body>
</html>
"""

    with open(filename, "w", encoding="utf-8") as file:
        file.write(new_content)

    return f"HTML 파일이 생성되었거나 업데이트되었습니다: {filename}"

def delete_platform(platform):
    filename = "user_info.html"
    if os.path.exists(filename):
        with open(filename, "r", encoding="utf-8") as file:
            content = file.read()
        
        # Extract the existing data
        data_start = content.find("var userData = ") + len("var userData = ")
        data_end = content.find("};", data_start) + 1
        user_data = json.loads(content[data_start:data_end])
        
        if platform in user_data:
            del user_data[platform]
            
            # Update the content
            new_data_json = json.dumps(user_data, indent=2)
            new_content = content[:data_start] + new_data_json + content[data_end:]
            
            with open(filename, "w", encoding="utf-8") as file:
                file.write(new_content)
            
            return True
    return False

def open_file_action():
    webbrowser.open("user_info.html")

class GUI:
    def __init__(self, master):
        self.master = master
        master.title("로그인 정보 관리")
        master.geometry("850x650")
        master.configure(bg='#f0f0f0')
        master.iconphoto(False, tk.PhotoImage(data="""iVBORw0KGgoAAAANSUhEUgAAAgAAAAIACAMAAADDpiTIAAAAA3NCSVQICAjb4U/gAAAACXBIWXMAAAztAAAM7QFl1Q
                                       BJAAAAGXRFWHRTb2Z0d2FyZQB3d3cuaW5rc2NhcGUub3Jnm+48GgAAAwBQTFRF////AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
                                       AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
                                       AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
                                       AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
                                       AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
                                       AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
                                       AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
                                       AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
                                       AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAACyO34QAAAP90
                                       Uk5TAAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8gISIjJCUmJygpKissLS4vMDEyMzQ1Njc4OTo7PD0+P0BBQkNERUZHSElKS0xNTk9QUVJTVFVWV1hZWltcXV5fYGFiY2RlZmdoaWprbG1ub3BxcnN0dXZ3eHl6e3
                                       x9fn+AgYKDhIWGh4iJiouMjY6PkJGSk5SVlpeYmZqbnJ2en6ChoqOkpaanqKmqq6ytrq+wsbKztLW2t7i5uru8vb6/wMHCw8TFxsfIycrLzM3Oz9DR0tPU1dbX2Nna29zd3t/g4eLj5OXm5+jp6uvs7e7v8PHy8/T19vf4+fr7
                                       /P3+6wjZNQAAFpRJREFUeNrt3Xd8FcXaB/BNBQIhKBBpQV5BOgTlEn3hlSpFxdA7oSkXgatwQYqgIogIqC++XIp0RPQCFwSkhCJGwSu9N6VIL4IkJISQ/tw/3o+ScpJndmd2Ocv8fn+fnTPnmW9O9szszhqGDQnuPHfjoRuZpF
                                       3iDi5uZOgev6gNyaRxjjbWe/wjj5PmSR+k8fBX2EEIfazt+De6idEnIhqp6fgPSMXYExFRZhctx787Rv6PJD+n4fjXTcLA/5nYqtqNf+hFDHuWnHtMNwCLMejZsrewXuMfnoExz551floB2IwRz5nZOo1/BMY7d0ZpBGAyhtvD
                                       dEBXfQCcxHB7mg5oqMv4V8Zge54OqKYJgB4Y6zymA0rpAWAEhjqP7NNjOmAaRjqvrNdiOmAZBjrPfKYDgGgPH3xAKT3CngCP1gDAJg+fW5cfwcXY6YBuAKA1AEppBABaA6C4agCgNQA6XwoAtAZA+wsDgNYAaIMfAGgNgOYAgN
                                       4A6C0A0BtAZncA0BoApTQGAK0BUFx1ANAaAJ0vDQBaA6D9RQBAawC00R8AtAZAcwFAbwA0BgD0BpDZAwC0BkApTQBAawAUVwMAtAZAF0oDgNYA6EARANAaAEX7A4DWAGgeAOgNgMYCgN4AqCcA6A0gpSkAaA2AbtcAAK0B0MUy
                                       AKA1ADoYDABaA6BN/gCgNQCaDwB6A6C3AUBvABQFAHoDSG0GAFoDoNs1AUBrAA/HdAAASORQMABoDYA2+wOA1gBoAQDoDYDeBQC9AVAvANAbgNunAwBANvG1AEBrAHSpLABoDcDd0wEAoCBb/AFAawC0EAD0BkDjAEBvANQbAP
                                       QGkPo8AGgNgOJrA4DWANw6HQAAynK4KABoDYC2BACA1gBoEQDoDYDeAwC9AVBfANAbQGpzANAagPumAwBAcS6XAwCtAdCRogCgNQDaGgAAWgOgxQCgNwAaDwB6A6B+AKA3gLQWAKA1AEoIBwCtAdCVMADQGgAdDQEArQHQtwEA
                                       oDUA+hwA9AZAEwBAbwD0CgDoDSCtJQBoDYAS6gCA1gBcMB0AAPbG66cDAMDmbAsAAK0B0BIA0BsAvQ8AegOgVwFAbwBprQBAawB05ykA0BoAXS0PAFoDoGMhAKA1APouEAC0BkBfAIDeAGgiAOgNgPoDgN4A0l4AAK0BeOd0AA
                                       A4GG+cDgAAJ3O8GABoDYBiAgFAawC01AcAtAZArwOA3gDiSgCA1gDoMwDQG0DGowCgNQBqBAB6AxgMAF6SkAcDYBYAeEt+fyAA1gCAt2TzAwGwCQC8JZMAQG8AkQCgNwCfGADQGoBR4Q4AaA3A6A8AegMwOt4EAK0BGKFfA4DW
                                       AAyjcrePY362KVc8lDcaAPRJV3wDAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
                                       AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAaA2gRJtBExdtPno+S+556OGVnxEbHxmTmPUF+9bNHf9aZAknRv/JN7dnEOKVSf9+aAV7R7/A8BMos3fn4OAA24bfN+oCCuz9OdvNx57xb3EQxXVH9je3YfgD
                                       56Gw7sm8QNXjX3I7quqmbC+pdvxrn0dN3ZXztZX++09ERd2WxBbqxr96POrpvsRXVzX+j55BNd2YM4+qGX//bailO7PNXwmA6aikW/MPFeNfLxOFdGsy6ykAEIM6ujcx8uP/Eqro5rwkvQB0FEV0c476SgLohRq6O70kAWxBCd
                                       2dLXLjXzQVJXR3UotKAeiCCro9XaQAfIkCuj1fSs0Cx6GAbk+czHxwDdTP/akhAaA5yuf+yFwg2Aflc3/6SAAYg/K5P2MkAMxA+dyfGRIAvkb53J+vFd/0i7gsmwAAAPQFkHn54I7olYtnTJ44be5Xa7ftPp6gHYBoTQHE/7R4
                                       TMfwoFyfqXSj/h+tPZn+wGVe37tq1icTxw4b1Ldr+54Dhr87ddbnqzb/eOhMkou/AW5uyjfHHatu0pbREX75frKQyGmHH8zFjpmnlo2NavxEnjfv+ZR/ftC0DafT3AiAeavXnKnw8fGNxG6NLNFx9k1Hxz79yOIhzwWLlT6gcu
                                       uR624DgNncnP4XMx8woN1ap654uDy/Q4jpC/LqDv8mDgCEk7oq0vz2GKF/P2z74Kf9MNryvZq+Tw/7EQBEkjI7zOqa105bO3bkDdl7tKpMuQYATJJnhkl80Bf22NWvhLkRSu7Pi1ybBgD5fPnPKCdZ4Zdt2QBnX7/Cqm7R9bkB
                                       AHnmpxryBfYdeld1t/a8ZKhLbfwLyHPKZ7CvkhJXjFHard0vKN2kZRgA5JHVZZV9yw5UN1G8q5XiXZo2AIDHJHZTWeXyu9T06lY/1Xv1BdwBAE/5tbbaOhf4QkWvlijeo8swjAb4Gegp3xZXXulR0lshn25mqM84APCQ//Wzod
                                       St5U4EMiYVtKFTxnYAyF3qVw1bUvO6RKdiX7SlT4VTASDX+PcxbEpN64uEh5+wp0utMBWca/x7GbalTqzFTi0NsqlHHwNAzvGPMmxMPUtbY6a9YVuHDgJAjvHvYdia+hY2x01tb1t3SmQCQPaMNGxOJ/PL0ZHe1JuHHMBSw/Z8
                                       ZHY9+kUbOzMHALIvsxW0H4CfuaWhpBZ2duYMAGTNVdPLP74h5j986GUzf//N7Bz/xwkAshb7GRMTKI16v7tw29lUSji8ZtobL9cws0bzrInJF1t/kxj9ACBrRgv3v/bMnD/nzgw3cX3eh8JdmmK5xL6PVKzXoM6TZULy28nlKw
                                       DIkr2CCwBBfTxe63lvkfAOyoVE//WuN39FSsiLH34Zvfv0rftLTymxl37+96LR7WsUyPXi6wCQ5ddWTaGuF5ya910VezsIfn7BLXKOm9yLr2SHTw/ks+aYcTZ6WoesX1Q1CQDu5x2hnlc/km8j8wqJFUDo6oBbFU1NMn52Umim
                                       a//Uln/MKw8BgPs5KLTrWX/uFssjVcT+Vm8JdKmTif/4bcws66bEDAgxDMNYBwB/JlPkzq9iK/iG7nQXqoDAH99q4XIGDTxl9vMmLW3m458AAH/mXyKruWIPOZxbQORU4grXTFxpwWI+9v7vlj7yuQUEAH8kvSrf6VIXBRv7Qq
                                       QEf+NaEb0qpUMsPZg8VAAWCvzN7hZu7S2BEhS4lH8b2wS//ecSAYD8HGB5tss+y0ycULQVqMHA/P9Hi/0CqHOSAEABgE/5Lo83015iON9gYL7/UT4SKaPP0GQCAAUA0vjzrW7mWrzwGF+Ed/ITFCryo2QjEQCoAMD/BAgzu8XS
                                       dn51qFw+G0pNFShiYAwBgBoA/JLr56bb7MxXIe+78hIF7gDyWUoAoAbAL+xfa7j5u3pO85vKtJNaBPyAAEARgGFsfzdbaHUQ26p/Xotxd0oITEoTACgCcI9dyW9hpdnr/B4eU/I4VODZzK3SAEAVAPbpR76HLLX7LluGZ/I4si
                                       7/+/8OAYAqAB253lp8ymkCeybn63l7nmP8CeA+AgBVAJKLcL21Wu2JFn9c8PcmeMVjFx8WABu5zj5pteVf2Tp09nRYRhnusIDTAKAOwACZGbv889/sBXxplgo7iABAGYBM9u/N+mbk09lCeJrMY68oKXwdANQB2M31tbb1tq+z
                                       1xm/l/ug9GD7vpIAIHcmcX2dJNE4+2zF1hZElkgAAIUA2KX7XyUaX8Q1Xjr3MZPtFAkAucKdAkTINH6bvTzwaq5j2I0gjwGAQgCXua4OkypSA675XFdmp3HTEmEEAAoBsE8/XCJVpMGmzwJ3ev8q0EMFgL0h9KhUkeZxzUeaPi
                                       ldBQAqATTlLt6VW3Xby1WiVs4juJ3g/eMBQCWAUkxP68oV6R53w1lIziMqMQc0JABQCCCZuxjoVckqsU+cyPGjPpWbO5oEACoBnOJ6Kvug+54mf9Sd5F5/AABUAtjK9fRHySp9zL1BdPbXr+X+ZYhs7HfedG7qCmA+11PZUy52
                                       sTnHRm3cDSFVRd7U/IB01RUAd9lWoOz3JDuzn2MioL+Kc0AAEE5vpqMlZQH8wpXizeyvb8S8vBMAKAXALddVkgXwm8mLO7h7QgcDgFIA9e2dBiBK4UrRO/vruXsCJwCAUgB1mI42lf6xFGTuO517+WcAoBTAk0xH20kD4JabX8
                                       r26nSucqsBQCkAbnj6SAOozrxD42yvvs1V7t8AoBRAMaajQ6QBcGcZ9bO9mr084TQAKAXA3cL7rjQA7tbzZuZmguMBQCWANK6jE6QBRDDv8LK55ePrAKASQCbX0eHSALidQ7PfHLRdyfUpACAcbmvfV6UBcBcc9DE3c/wdACgF
                                       wD0iuJM0AI5Y9pnAI1zllgOAUgBhTEdbyI5/qrm1gNNKrk8AAGX/oZ+RBXCTK0X23xmXTC4eAoAkgKdULL/nlzNcKaZme/nv3MuxGKQWAHfjRmlZAPu5Uvwz28vvci/vDABKAXB3BgbJAviOK8VP2V6ewb28CQAoBcA+lTlVEs
                                       AC7g1yPDeA22K2OgAoBcBes3lEEsDrTPuBObag5B5d6BcHACoBrOB6ulgSQEOm/Yo5Xs/uMLsaAFQC2MX19HVJANyjZXNecTJCxc8AABDOVa6nDeTG/xzXft8cB8zkDqgi8K4VPORxAPC4GhTI9LRwhhSANVwlcj5Fdj1bu0vW
                                       epIMAB7DXRRonJACMJ5rfmuOA/hdQhcBgEoAr3BdlduVvx3XfM5HfqWyjx7tAQAqAczmuiq3RUwFpvXc9x08x3WoFACoBLCH62p9mfE/av7sm98o+AAAKASQzF0V6HNJovW3uUJ8kusQ/oGx3QBAIQB2PTDHcp25cLcdGD/kOu
                                       Q6WzzfXwBAIQB2r+hwG5cCAzw89+EJtnq9AEAhAHafOImNGdn/5808HMTuKWL4nQEAdQDucFNBxluW236ca3q6leUJw+gHAOoA8Bs6V8i02DK756Ph6Xn0d4PYw/zPAYA6APxzg63uE8RuE+p5J/qOfP3+CgDqALAX4lr83UUX
                                       CnINe974fzlfv4DdAKAMAHtlsOHzk6V2e7Fl2OvxuMRCfAHDbgCAMgDsgo0RYeUs4LCv1ZOL9gIVbJoOAKoAXGIf7GLh2dEC+/4bk/M4co1ICUcCgCoA1JrtbxnzD+r8lm20QF67M2ZUEqnhSgBQBWAt3+ExZtvM5B//mveE3g
                                       yRGgafAABFANLLsh0uaPbJQbP5IuzJ8+DER0SKWPU3AFADgN7hexxubs/YHwLYFuvlc/hooSqG7QMANQCuCfzwet7MLSJnivMN5ndieSVAqIyFlgKAEgD0d4E+9xD/LXi7Gt9c5XwfRdJfsJBvpgOACgAiXwHGKOFzipYCrf0r
                                       3yZuhAhWskUsACgAQMNEev0PwcZeF2irHtPGNNFSVtoNAAoAXA8S6LXvJJGbBBK6i1RgG9NKWnXhYkYeAAD5jBDqd8MLbEP7hWZx+K1ntopX06fdYQCQTUI5oY6HfMUtLgeKNOMn8EfbzkQ9fToe0xlA39tWkmh6OvD/fwzczq
                                       ejtyLFGhktcmL6mJmK+rZdcElbANbSKsebdBQ8rtzEvCr9y/DiYk3UShFaTfA1+YmqDdmQmEdbd6KHAwAD4Gox4b+2Vityj2DKsiaixwccEvvY48x/qMDGHyz77tiNLCerKb+d2vzWs9zzKwGAiOaYOLj4G9t+vT81mHp228iS
                                       4gdPFPzYGc2sfjbf0JpNu3RqEVGlVEGxAwCAiDLbmqxy2fpdR306pkeDcua+qyOEZ++ulzIcCgAQEcVXcaLWoefEP/jOwgDgIAA6UcT+UhfcaeaTby0AAA4CoJW2V9pnubmPvtofABwEQKPsrvQHZsu8xAcAHASQ0dveQvc2X+
                                       eZAOAgAMrobmede6ZZKPSXBQDAOQCU3sm+Mg+0dpfhjuIA4BwASmtnV5VHksWcqQwAzgGg1G72FHkiWU5sYwBwDgDRJF/1b1dwvsxqdepYPwBwDgB9E6z63aocJrnsrgoAzgGg45XUvlmPOySbpKE+AOAYAIrtrPCtCs0jFfm+
                                       IgA4BoBotbKluOY/k5qkziwNAI4BoNg+St6n/CpSl7tTHgUApwAQbfov6XcpMPYuKc3td2xYsqwwCwA8f+fOCZN6D/+o06Q88bOeVlkH3/ofHrXUDx0AEKXMLGv5HQoPvUD2ZP9rRdUUoWinJTetdkIPAET3PrV28h36fizZl7
                                       uLXgiSLECZDp/slHkqni4AiGjHK2b/4II6rbxHNid5y/AaVv811f3bV+dl318jAERJS5uLz8UWbL8skZzJpflRtcxdM1Tkqa4fxCjpnoMAdj5rQ4aaPf1eO6QWPxdXoP6INQnkaJL3zRtcn/9p4F+59bA5MVfUva+DALwmN1YM
                                       apjn/FBg5TZTfkx+QD3LvLZv7ey3+7aoGRp8f3cRn+Cy1Z9t2emVYe/937pTaarfUkcARESUsP+f46NeblKvWtgjAQHFylZ+6n9adhuzIOZChrd0MOPurStnjx+7eNveHmkLAAEABAAQAAAAAAAAAAAAC1mJ8rk/MjdSTkf53J
                                       /pEgBGoXzuj8yNtFEon/sTJQGgGcrn/jSTAFAV5XN/ZO5U8b2B+rk9N6Tun1uIAro9C6Uux2mDAro9baQABCWhgu5OkuQ1qd+ghO7ON5KXZHZACd2dDrIX5e5CDd2cXdJXZTdEEd2chvLX5eMsQOMzAMMwjOrpqKNbk15dAQBj
                                       HArp1oxTMf6GzwpU0p1ZoWi3oqD9qKUbsz/IUJRy11BN9+VaOUNZnoYA942/0v1Jwg6gou7KgTBDaYJwgbCrsjLIUByfCZkoq1uSOcGO3UrDo1FZdyQ63LAnTfaguN6fPU0M+9IhOgUV9uakRHcw7E3RLsviUWfvTPyyrkUNBx
                                       IY0XbghHnrv88ST1vtnfgeUZQTHsobm/UF6+dNGNg2ItB4YPF0G3FXA1EUT3tEb/KqHgIAAAAAAAAAAAAAAAAAAAAAAAAAAGDgAAABAAQAEABAAAABAAQAEABAAAABAAQAEABAAAABAAQAEABAAAABAAQAEABAAAABAAQAEABA
                                       AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
                                       AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAMHAAgGgMYO1kRFHWuhIAYmsAAAAAAAAAAAC8ItEYEKcT7VUAlmNAnM5yrwIwDQPidKZ5FYARGBCnM8KrAPTEgDidnl4FoDIG
                                       xOlU9q7Z6pMYEWdz0suWKyZjSJzNZC8DEIEhcTYR3rZiuRlj4mQ2e92SdXgGRsW5ZIR730ULizEszmWxF161EnoR4+JULoZ643VLdZMwMs4kqa53XrnWHUPjTLp767WLA1IxOPYndYD3Xr3a6CbGx+7cbOTN1y9X2IERsjfbK3
                                       j5JeyRxzFI9uVoa++/icEvakMyRsqOJK/v7uuOG1mCO8/deOhGJoZMVTJvHNo4t3MRO8bqP+lm959ipwKIAAAAAElFTkSuQmCC"""))

        style = ttk.Style()
        style.theme_use('clam')

        # 상단 프레임
        top_frame = ttk.Frame(master, padding="10")
        top_frame.pack(fill=tk.X)

        # 왼쪽 프레임 (입력 폼)
        left_frame = ttk.Frame(top_frame, padding="10", width=300)
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        ttk.Label(left_frame, text="새 로그인 정보 추가", font=('Helvetica', 16, 'bold')).pack(pady=10)

        self.platform_var = tk.StringVar()
        self.username_var = tk.StringVar()
        self.password_var = tk.StringVar()

        ttk.Label(left_frame, text="플랫폼:").pack(anchor='w', pady=5)
        ttk.Entry(left_frame, textvariable=self.platform_var).pack(fill=tk.X, pady=5)

        ttk.Label(left_frame, text="아이디:").pack(anchor='w', pady=5)
        ttk.Entry(left_frame, textvariable=self.username_var).pack(fill=tk.X, pady=5)

        ttk.Label(left_frame, text="비밀번호:").pack(anchor='w', pady=5)
        ttk.Entry(left_frame, textvariable=self.password_var, show="*").pack(fill=tk.X, pady=5)

        ttk.Button(left_frame, text="저장", command=self.submit).pack(pady=10)
        ttk.Button(left_frame, text="파일 열기", command=open_file_action).pack(pady=5)
        ttk.Button(left_frame, text="서버 열기", command=self.open_server).pack(pady=5)

        # 오른쪽 프레임 (플랫폼 목록)
        right_frame = ttk.Frame(top_frame, padding="10", width=300)
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        ttk.Label(right_frame, text="저장된 플랫폼", font=('Helvetica', 16, 'bold')).pack(pady=10)

        self.platform_listbox = tk.Listbox(right_frame)
        self.platform_listbox.pack(fill=tk.BOTH, expand=True)

        button_frame = ttk.Frame(right_frame)
        button_frame.pack(pady=10)

        ttk.Button(button_frame, text="삭제", command=self.delete).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="이름 변경", command=self.rename_platform).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="새로고침", command=self.refresh_platform_list).pack(side=tk.LEFT, padx=5)

        # 하단 프레임 (서버 로그)
        bottom_frame = ttk.Frame(master)
        bottom_frame.pack(fill=tk.BOTH, expand=True)

        self.log_text = scrolledtext.ScrolledText(bottom_frame, height=10)
        self.log_text.pack(fill=tk.BOTH, expand=True)
        
        ttk.Label(bottom_frame, text="서버 로그", font=('Helvetica', 16, 'bold')).pack(pady=10)

        # 로거 설정
        self.setup_logger()

        self.refresh_platform_list()
        
        threading.Thread(target=self.run_server, daemon=True).start()
        logging.getLogger('tkinter_logger').info("Server started: http://localhost:5000")
        
    def setup_logger(self):
        logger = logging.getLogger('tkinter_logger')
        logger.setLevel(logging.INFO)
        
        tk_handler = TkinterHandler(self.log_text)
        tk_handler.setLevel(logging.INFO)
        
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        tk_handler.setFormatter(formatter)
        
        logger.addHandler(tk_handler)

        # Flask 앱 로거에 핸들러 추가
        app.logger.addHandler(tk_handler)
    def submit(self):
        platform = self.platform_var.get()
        username = self.username_var.get()
        password = self.password_var.get()

        if not platform or not username or not password:
            messagebox.showerror("오류", "모든 필드를 입력해주세요.")
            return

        result = create_or_update_html(platform, username, password)
        if result == "update_query":
            if messagebox.askyesno("업데이트", "이미 존재하는 플랫폼입니다. 업데이트하시겠습니까?"):
                create_or_update_html(platform, username, password, update=True)
                logging.getLogger('tkinter_logger').info(f"Successfully updated user login information")
                messagebox.showinfo("성공", "로그인 정보가 업데이트되었습니다.")
            else:
                messagebox.showinfo("취소", "업데이트가 취소되었습니다.")
        else:
            logging.getLogger('tkinter_logger').info(f"Successfully saved user login information")
            messagebox.showinfo("성공", "로그인 정보가 저장되었습니다.")

        self.clear_entries()
        self.refresh_platform_list()

    def delete(self):
        selection = self.platform_listbox.curselection()
        if selection:
            platform = self.platform_listbox.get(selection[0])
            if messagebox.askyesno("삭제 확인", f"{platform} 플랫폼을 삭제하시겠습니까?"):
                if delete_platform(platform):
                    logging.getLogger('tkinter_logger').info(f"Delete Platform {platform} Successful")
                    messagebox.showinfo("성공", f"{platform} 플랫폼이 삭제되었습니다.")
                    self.refresh_platform_list()
                else:
                    logging.getLogger('tkinter_logger').info(f"Failed to delete platform {platform}")
                    messagebox.showerror("오류", f"{platform} 플랫폼을 삭제하는 데 실패했습니다.")
        else:
            messagebox.showwarning("경고", "삭제할 플랫폼을 선택해주세요.")

    def clear_entries(self):
        self.platform_var.set("")
        self.username_var.set("")
        self.password_var.set("")

    def refresh_platform_list(self):
        filename = "user_info.html"
        self.platform_listbox.delete(0, tk.END)
        if os.path.exists(filename):
            with open(filename, "r", encoding="utf-8") as file:
                content = file.read()
            data_start = content.find("var userData = ") + len("var userData = ")
            data_end = content.find("};", data_start) + 1
            user_data = json.loads(content[data_start:data_end])
            for platform in user_data.keys():
                self.platform_listbox.insert(tk.END, platform)

    def rename_platform(self):
        selection = self.platform_listbox.curselection()
        if selection:
            old_platform = self.platform_listbox.get(selection[0])
            new_platform = simpledialog.askstring("이름 변경", f"{old_platform}의 새 이름을 입력하세요:")
            if new_platform:
                if self.update_platform_name(old_platform, new_platform):
                    logging.getLogger('tkinter_logger').info(f"Platform name updated: {old_platform} -> {new_platform}")
                    messagebox.showinfo("성공", f"{old_platform}의 이름이 {new_platform}(으)로 변경되었습니다.")
                    self.refresh_platform_list()
                else:
                    logging.getLogger('tkinter_logger').info(f"Failed to update platform name: {old_platform} -> {new_platform}")
                    messagebox.showerror("오류", "플랫폼 이름 변경에 실패했습니다.")
        else:
            messagebox.showwarning("경고", "이름을 변경할 플랫폼을 선택해주세요.")

    def update_platform_name(self, old_platform, new_platform):
        filename = "user_info.html"
        if os.path.exists(filename):
            with open(filename, "r", encoding="utf-8") as file:
                content = file.read()
            
            data_start = content.find("var userData = ") + len("var userData = ")
            data_end = content.find("};", data_start) + 1
            user_data = json.loads(content[data_start:data_end])
            
            if old_platform in user_data:
                user_data[new_platform] = user_data.pop(old_platform)
                
                new_data_json = json.dumps(user_data, indent=2)
                new_content = content[:data_start] + new_data_json + content[data_end:]
                
                with open(filename, "w", encoding="utf-8") as file:
                    file.write(new_content)
                return True
    
        return False
    
    def open_server(self):
        webbrowser.open("http://localhost:5000")

    def run_server(self):
        run_flask()

if __name__ == "__main__":
    root = tk.Tk()
    gui = GUI(root)
    root.mainloop()