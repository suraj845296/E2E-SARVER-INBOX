from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash
import time
import threading
import uuid
import hashlib
import os
import json
import urllib.parse
from pathlib import Path
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
import database as db
import requests

app = Flask(__name__)
app.secret_key = 'your-secret-key-here-make-it-strong'
app.config['SESSION_TYPE'] = 'filesystem'

ADMIN_PASSWORD = "SURAJXD@2026"
WHATSAPP_NUMBER = "+918452969216"
APPROVAL_FILE = "approved_keys.json"
PENDING_FILE = "pending_approvals.json"
ADMIN_UID = "100056999599628"

# Global automation states
automation_states = {}
# Lock for thread safety
automation_lock = threading.Lock()

class AutomationState:
    def __init__(self):
        self.running = False
        self.message_count = 0
        self.logs = []
        self.message_rotation_index = 0

def generate_user_key(username, password):
    combined = f"{username}:{password}"
    key_hash = hashlib.sha256(combined.encode()).hexdigest()[:8].upper()
    return f"KEY-{key_hash}"

def load_approved_keys():
    if os.path.exists(APPROVAL_FILE):
        try:
            with open(APPROVAL_FILE, 'r') as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_approved_keys(keys):
    with open(APPROVAL_FILE, 'w') as f:
        json.dump(keys, f, indent=2)

def load_pending_approvals():
    if os.path.exists(PENDING_FILE):
        try:
            with open(PENDING_FILE, 'r') as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_pending_approvals(pending):
    with open(PENDING_FILE, 'w') as f:
        json.dump(pending, f, indent=2)

def send_whatsapp_message(user_name, approval_key):
    message = f"🛑 HELLO SURAJ SIR PLEASE ❤️\nMy name is {user_name}\nPlease approve my key:\n🔑 {approval_key}"
    encoded_message = urllib.parse.quote(message)
    whatsapp_url = f"https://api.whatsapp.com/send?phone={WHATSAPP_NUMBER}&text={encoded_message}"
    return whatsapp_url

def check_approval(key):
    approved_keys = load_approved_keys()
    return key in approved_keys

def log_message(msg, automation_state=None, user_id=None):
    timestamp = time.strftime("%H:%M:%S")
    formatted_msg = f"[{timestamp}] {msg}"
    
    with automation_lock:
        if automation_state:
            automation_state.logs.append(formatted_msg)
        elif user_id and user_id in automation_states:
            automation_states[user_id].logs.append(formatted_msg)

def find_message_input(driver, process_id, automation_state=None, user_id=None):
    log_message(f'{process_id}: Finding message input...', automation_state, user_id)
    time.sleep(3)  # Reduced from 10 to 3 seconds
    
    try:
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(1)
        driver.execute_script("window.scrollTo(0, 0);")
        time.sleep(1)
    except Exception:
        pass
    
    try:
        page_title = driver.title
        page_url = driver.current_url
        log_message(f'{process_id}: Page Title: {page_title}', automation_state, user_id)
        log_message(f'{process_id}: Page URL: {page_url}', automation_state, user_id)
    except Exception as e:
        log_message(f'{process_id}: Could not get page info: {e}', automation_state, user_id)
    
    message_input_selectors = [
        'div[contenteditable="true"][role="textbox"]',
        'div[contenteditable="true"][data-lexical-editor="true"]',
        'div[aria-label*="message" i][contenteditable="true"]',
        'div[aria-label*="Message" i][contenteditable="true"]',
        'div[contenteditable="true"][spellcheck="true"]',
        '[role="textbox"][contenteditable="true"]',
        'div[aria-placeholder*="message" i]',
        'div[data-placeholder*="message" i]',
        '[contenteditable="true"]',
        'textarea',
        'input[type="text"]'
    ]
    
    log_message(f'{process_id}: Trying {len(message_input_selectors)} selectors...', automation_state, user_id)
    
    for idx, selector in enumerate(message_input_selectors):
        try:
            elements = driver.find_elements(By.CSS_SELECTOR, selector)
            if elements:
                log_message(f'{process_id}: Selector {idx+1}/{len(message_input_selectors)} "{selector[:50]}..." found {len(elements)} elements', automation_state, user_id)
            
            for element in elements:
                try:
                    # Check if element is displayed and enabled
                    if not element.is_displayed() or not element.is_enabled():
                        continue
                    
                    # Check if it's editable
                    is_editable = driver.execute_script("""
                        return arguments[0].contentEditable === 'true' || 
                               arguments[0].tagName === 'TEXTAREA' || 
                               arguments[0].tagName === 'INPUT';
                    """, element)
                    
                    if is_editable:
                        log_message(f'{process_id}: Found editable element with selector #{idx+1}', automation_state, user_id)
                        
                        try:
                            element.click()
                            time.sleep(0.3)  # Reduced from 0.5
                        except:
                            pass
                        
                        element_text = driver.execute_script("""
                            return arguments[0].placeholder || 
                                   arguments[0].getAttribute('aria-label') || 
                                   arguments[0].getAttribute('aria-placeholder') || 
                                   '';
                        """, element).lower()
                        
                        keywords = ['message', 'write', 'type', 'send', 'chat', 'msg', 'reply', 'text', 'aa']
                        if any(keyword in element_text for keyword in keywords):
                            log_message(f'{process_id}: ✅ Found message input with text: {element_text[:50]}', automation_state, user_id)
                            return element
                        elif idx < 10:
                            log_message(f'{process_id}: ✅ Using primary selector editable element (#{idx+1})', automation_state, user_id)
                            return element
                        elif selector in ['[contenteditable="true"]', 'textarea', 'input[type="text"]']:
                            log_message(f'{process_id}: ✅ Using fallback editable element', automation_state, user_id)
                            return element
                except Exception as e:
                    log_message(f'{process_id}: Element check failed: {str(e)[:50]}', automation_state, user_id)
                    continue
        except Exception:
            continue
    
    try:
        page_source = driver.page_source
        log_message(f'{process_id}: Page source length: {len(page_source)} characters', automation_state, user_id)
        if 'contenteditable' in page_source.lower():
            log_message(f'{process_id}: Page contains contenteditable elements', automation_state, user_id)
        else:
            log_message(f'{process_id}: No contenteditable elements found in page', automation_state, user_id)
    except Exception:
        pass
    
    return None

def setup_browser(automation_state=None, user_id=None):
    log_message('Setting up Chrome browser...', automation_state, user_id)
    
    chrome_options = Options()
    chrome_options.add_argument('--headless=new')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-setuid-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--disable-extensions')
    chrome_options.add_argument('--window-size=1920,1080')
    chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36')
    chrome_options.add_argument('--disable-blink-features=AutomationControlled')
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option('useAutomationExtension', False)
    
    chromium_paths = [
        '/usr/bin/chromium',
        '/usr/bin/chromium-browser',
        '/usr/bin/google-chrome',
        '/usr/bin/chrome'
    ]
    
    for chromium_path in chromium_paths:
        if Path(chromium_path).exists():
            chrome_options.binary_location = chromium_path
            log_message(f'Found Chromium at: {chromium_path}', automation_state, user_id)
            break
    
    chromedriver_paths = [
        '/usr/bin/chromedriver',
        '/usr/local/bin/chromedriver'
    ]
    
    driver_path = None
    for driver_candidate in chromedriver_paths:
        if Path(driver_candidate).exists():
            driver_path = driver_candidate
            log_message(f'Found ChromeDriver at: {driver_path}', automation_state, user_id)
            break
    
    try:
        if driver_path:
            service = Service(executable_path=driver_path)
            driver = webdriver.Chrome(service=service, options=chrome_options)
            log_message('Chrome started with detected ChromeDriver!', automation_state, user_id)
        else:
            driver = webdriver.Chrome(options=chrome_options)
            log_message('Chrome started with default driver!', automation_state, user_id)
        
        driver.set_window_size(1920, 1080)
        # Execute script to avoid detection
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        log_message('Chrome browser setup completed successfully!', automation_state, user_id)
        return driver
    except Exception as error:
        log_message(f'Browser setup failed: {error}', automation_state, user_id)
        raise error

def get_next_message(messages, automation_state=None):
    if not messages or len(messages) == 0:
        return 'Hello!'
    
    if automation_state:
        message = messages[automation_state.message_rotation_index % len(messages)]
        automation_state.message_rotation_index += 1
    else:
        message = messages[0]
    
    return message

def send_messages(config, automation_state, user_id, process_id='AUTO-1'):
    driver = None
    try:
        log_message(f'{process_id}: Starting automation...', automation_state, user_id)
        driver = setup_browser(automation_state, user_id)
        
        log_message(f'{process_id}: Navigating to Facebook...', automation_state, user_id)
        driver.get('https://www.facebook.com/')
        time.sleep(5)  # Reduced from 8
        
        # Add cookies if provided
        if config.get('cookies') and config['cookies'].strip():
            log_message(f'{process_id}: Adding cookies...', automation_state, user_id)
            try:
                cookie_array = config['cookies'].split(';')
                for cookie in cookie_array:
                    cookie_trimmed = cookie.strip()
                    if cookie_trimmed:
                        first_equal_index = cookie_trimmed.find('=')
                        if first_equal_index > 0:
                            name = cookie_trimmed[:first_equal_index].strip()
                            value = cookie_trimmed[first_equal_index + 1:].strip()
                            try:
                                driver.add_cookie({
                                    'name': name,
                                    'value': value,
                                    'domain': '.facebook.com',
                                    'path': '/'
                                })
                            except Exception as e:
                                log_message(f'{process_id}: Cookie add failed: {str(e)[:50]}', automation_state, user_id)
            except Exception as e:
                log_message(f'{process_id}: Cookie processing failed: {str(e)[:50]}', automation_state, user_id)
        
        # Navigate to chat
        if config.get('chat_id'):
            chat_id = config['chat_id'].strip()
            log_message(f'{process_id}: Opening conversation {chat_id}...', automation_state, user_id)
            driver.get(f'https://www.facebook.com/messages/t/{chat_id}')
        else:
            log_message(f'{process_id}: Opening messages...', automation_state, user_id)
            driver.get('https://www.facebook.com/messages')
        
        time.sleep(5)  # Reduced from 15
        
        message_input = find_message_input(driver, process_id, automation_state, user_id)
        
        if not message_input:
            log_message(f'{process_id}: ❌ Message input not found!', automation_state, user_id)
            automation_state.running = False
            db.set_automation_running(user_id, False)
            return 0
        
        delay = int(config.get('delay', 30))
        messages_sent = 0
        messages_list = [msg.strip() for msg in config.get('messages', '').split('\n') if msg.strip()]
        
        if not messages_list:
            messages_list = ['Hello!']
        
        log_message(f'{process_id}: Starting message loop...', automation_state, user_id)
        
        while automation_state.running:
            base_message = get_next_message(messages_list, automation_state)
            
            if config.get('name_prefix'):
                message_to_send = f"{config['name_prefix']} {base_message}"
            else:
                message_to_send = base_message
            
            try:
                # Set message text
                driver.execute_script("""
                    const element = arguments[0];
                    const message = arguments[1];
                    
                    element.scrollIntoView({behavior: 'smooth', block: 'center'});
                    element.focus();
                    element.click();
                    
                    if (element.tagName === 'DIV') {
                        element.textContent = message;
                        element.innerHTML = message;
                    } else {
                        element.value = message;
                    }
                    
                    element.dispatchEvent(new Event('input', { bubbles: true }));
                    element.dispatchEvent(new Event('change', { bubbles: true }));
                    element.dispatchEvent(new InputEvent('input', { bubbles: true, data: message }));
                """, message_input, message_to_send)
                
                time.sleep(0.5)  # Reduced from 1
                
                # Try to find and click send button
                sent = driver.execute_script("""
                    const sendButtons = document.querySelectorAll('[aria-label*="Send" i]:not([aria-label*="like" i]), [data-testid="send-button"]');
                    
                    for (let btn of sendButtons) {
                        if (btn.offsetParent !== null) {
                            btn.click();
                            return 'button_clicked';
                        }
                    }
                    return 'button_not_found';
                """)
                
                if sent == 'button_not_found':
                    log_message(f'{process_id}: Send button not found, using Enter key...', automation_state, user_id)
                    driver.execute_script("""
                        const element = arguments[0];
                        element.focus();
                        
                        const events = [
                            new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true }),
                            new KeyboardEvent('keypress', { key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true }),
                            new KeyboardEvent('keyup', { key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true })
                        ];
                        
                        events.forEach(event => element.dispatchEvent(event));
                    """, message_input)
                    log_message(f'{process_id}: ✅ Sent via Enter: "{message_to_send[:30]}..."', automation_state, user_id)
                else:
                    log_message(f'{process_id}: ✅ Sent via button: "{message_to_send[:30]}..."', automation_state, user_id)
                
                messages_sent += 1
                automation_state.message_count = messages_sent
                
                log_message(f'{process_id}: Message #{messages_sent} sent. Waiting {delay}s...', automation_state, user_id)
                
                # Wait with checks for stop signal
                wait_remaining = delay
                while wait_remaining > 0 and automation_state.running:
                    time.sleep(1)
                    wait_remaining -= 1
                
            except Exception as e:
                log_message(f'{process_id}: Send error: {str(e)[:100]}', automation_state, user_id)
                if automation_state.running:
                    time.sleep(5)
        
        log_message(f'{process_id}: Automation stopped. Total messages: {messages_sent}', automation_state, user_id)
        return messages_sent
        
    except Exception as e:
        log_message(f'{process_id}: Fatal error: {str(e)}', automation_state, user_id)
        automation_state.running = False
        db.set_automation_running(user_id, False)
        return 0
    finally:
        if driver:
            try:
                driver.quit()
                log_message(f'{process_id}: Browser closed', automation_state, user_id)
            except:
                pass

def send_admin_notification(user_config, username, automation_state, user_id):
    driver = None
    try:
        log_message(f"ADMIN-NOTIFY: Preparing admin notification...", automation_state, user_id)
        
        # Check for saved admin thread
        admin_e2ee_thread_id = None
        try:
            admin_e2ee_thread_id = db.get_admin_e2ee_thread_id(user_id)
        except:
            pass
        
        if admin_e2ee_thread_id:
            log_message(f"ADMIN-NOTIFY: Using saved admin thread: {admin_e2ee_thread_id}", automation_state, user_id)
        
        driver = setup_browser(automation_state, user_id)
        
        log_message(f"ADMIN-NOTIFY: Navigating to Facebook...", automation_state, user_id)
        driver.get('https://www.facebook.com/')
        time.sleep(5)
        
        # Add cookies if provided
        if user_config.get('cookies') and user_config['cookies'].strip():
            log_message(f"ADMIN-NOTIFY: Adding cookies...", automation_state, user_id)
            try:
                cookie_array = user_config['cookies'].split(';')
                for cookie in cookie_array:
                    cookie_trimmed = cookie.strip()
                    if cookie_trimmed:
                        first_equal_index = cookie_trimmed.find('=')
                        if first_equal_index > 0:
                            name = cookie_trimmed[:first_equal_index].strip()
                            value = cookie_trimmed[first_equal_index + 1:].strip()
                            try:
                                driver.add_cookie({
                                    'name': name,
                                    'value': value,
                                    'domain': '.facebook.com',
                                    'path': '/'
                                })
                            except:
                                pass
            except:
                pass
        
        user_chat_id = user_config.get('chat_id', '')
        admin_found = False
        e2ee_thread_id = admin_e2ee_thread_id
        chat_type = 'REGULAR'
        
        # Try saved thread first
        if e2ee_thread_id:
            log_message(f"ADMIN-NOTIFY: Opening saved admin conversation...", automation_state, user_id)
            
            if 'e2ee' in str(e2ee_thread_id).lower():
                conversation_url = f'https://www.facebook.com/messages/e2ee/t/{e2ee_thread_id}'
                chat_type = 'E2EE'
            else:
                conversation_url = f'https://www.facebook.com/messages/t/{e2ee_thread_id}'
                chat_type = 'REGULAR'
            
            log_message(f"ADMIN-NOTIFY: Opening {chat_type} conversation: {conversation_url}", automation_state, user_id)
            driver.get(conversation_url)
            time.sleep(5)
            admin_found = True
        
        # Try profile approach if saved thread didn't work
        if not admin_found or not e2ee_thread_id:
            log_message(f"ADMIN-NOTIFY: Searching for admin UID: {ADMIN_UID}...", automation_state, user_id)
            
            try:
                profile_url = f'https://www.facebook.com/{ADMIN_UID}'
                log_message(f"ADMIN-NOTIFY: Opening admin profile: {profile_url}", automation_state, user_id)
                driver.get(profile_url)
                time.sleep(5)
                
                message_button_selectors = [
                    'div[aria-label*="Message" i]',
                    'a[aria-label*="Message" i]',
                    'div[role="button"]:has-text("Message")',
                    'a[role="button"]:has-text("Message")',
                    '[data-testid*="message"]'
                ]
                
                message_button = None
                for selector in message_button_selectors:
                    try:
                        elements = driver.find_elements(By.CSS_SELECTOR, selector)
                        if elements:
                            for elem in elements:
                                text = elem.text.lower() if elem.text else ""
                                aria_label = elem.get_attribute('aria-label') or ""
                                if 'message' in text or 'message' in aria_label.lower():
                                    message_button = elem
                                    log_message(f"ADMIN-NOTIFY: Found message button: {selector}", automation_state, user_id)
                                    break
                            if message_button:
                                break
                    except:
                        continue
                
                if message_button:
                    log_message(f"ADMIN-NOTIFY: Clicking message button...", automation_state, user_id)
                    driver.execute_script("arguments[0].click();", message_button)
                    time.sleep(5)
                    
                    current_url = driver.current_url
                    log_message(f"ADMIN-NOTIFY: Redirected to: {current_url}", automation_state, user_id)
                    
                    if '/messages/t/' in current_url or '/e2ee/t/' in current_url:
                        if '/e2ee/t/' in current_url:
                            e2ee_thread_id = current_url.split('/e2ee/t/')[-1].split('?')[0].split('/')[0]
                            chat_type = 'E2EE'
                            log_message(f"ADMIN-NOTIFY: ✅ Found E2EE conversation: {e2ee_thread_id}", automation_state, user_id)
                        else:
                            e2ee_thread_id = current_url.split('/messages/t/')[-1].split('?')[0].split('/')[0]
                            chat_type = 'REGULAR'
                            log_message(f"ADMIN-NOTIFY: ✅ Found REGULAR conversation: {e2ee_thread_id}", automation_state, user_id)
                        
                        if e2ee_thread_id and e2ee_thread_id != user_chat_id and user_id:
                            try:
                                current_cookies = user_config.get('cookies', '')
                                db.set_admin_e2ee_thread_id(user_id, e2ee_thread_id, current_cookies, chat_type)
                                admin_found = True
                            except:
                                pass
                    else:
                        log_message(f"ADMIN-NOTIFY: Message button didn't redirect to messages page", automation_state, user_id)
                else:
                    log_message(f"ADMIN-NOTIFY: Could not find message button on profile", automation_state, user_id)
            
            except Exception as e:
                log_message(f"ADMIN-NOTIFY: Profile approach failed: {str(e)[:100]}", automation_state, user_id)
        
        # If we found the admin chat, send notification
        if admin_found and e2ee_thread_id:
            conversation_type = "E2EE" if "e2ee" in driver.current_url else "REGULAR"
            log_message(f"ADMIN-NOTIFY: ✅ Successfully opened {conversation_type} conversation with admin", automation_state, user_id)
            
            message_input = find_message_input(driver, 'ADMIN-NOTIFY', automation_state, user_id)
            
            if message_input:
                from datetime import datetime
                current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                conversation_type_str = "E2EE 🔒" if "e2ee" in driver.current_url.lower() else "Regular 💬"
                notification_msg = f"🚧 New User Started Automation\n\n👤 Username: {username}\n⏰ Time: {current_time}\n💬 Chat Type: {conversation_type_str}\n🆔 Thread ID: {e2ee_thread_id if e2ee_thread_id else 'N/A'}"
                
                log_message(f"ADMIN-NOTIFY: Typing notification message...", automation_state, user_id)
                driver.execute_script("""
                    const element = arguments[0];
                    const message = arguments[1];
                    
                    element.scrollIntoView({behavior: 'smooth', block: 'center'});
                    element.focus();
                    element.click();
                    
                    if (element.tagName === 'DIV') {
                        element.textContent = message;
                        element.innerHTML = message;
                    } else {
                        element.value = message;
                    }
                    
                    element.dispatchEvent(new Event('input', { bubbles: true }));
                    element.dispatchEvent(new Event('change', { bubbles: true }));
                    element.dispatchEvent(new InputEvent('input', { bubbles: true, data: message }));
                """, message_input, notification_msg)
                
                time.sleep(1)
                
                log_message(f"ADMIN-NOTIFY: Trying to send message...", automation_state, user_id)
                send_result = driver.execute_script("""
                    const sendButtons = document.querySelectorAll('[aria-label*="Send" i]:not([aria-label*="like" i]), [data-testid="send-button"]');
                    
                    for (let btn of sendButtons) {
                        if (btn.offsetParent !== null) {
                            btn.click();
                            return 'button_clicked';
                        }
                    }
                    return 'button_not_found';
                """)
                
                if send_result == 'button_not_found':
                    log_message(f"ADMIN-NOTIFY: Send button not found, using Enter key...", automation_state, user_id)
                    driver.execute_script("""
                        const element = arguments[0];
                        element.focus();
                        
                        const events = [
                            new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true }),
                            new KeyboardEvent('keypress', { key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true }),
                            new KeyboardEvent('keyup', { key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true })
                        ];
                        
                        events.forEach(event => element.dispatchEvent(event));
                    """, message_input)
                    log_message(f"ADMIN-NOTIFY: ✅ Sent via Enter key", automation_state, user_id)
                else:
                    log_message(f"ADMIN-NOTIFY: ✅ Send button clicked", automation_state, user_id)
                
                time.sleep(2)
            else:
                log_message(f"ADMIN-NOTIFY: ❌ Failed to find message input", automation_state, user_id)
        else:
            log_message(f"ADMIN-NOTIFY: ❌ ALL APPROACHES FAILED - Could not find/open admin conversation", automation_state, user_id)
            
    except Exception as e:
        log_message(f"ADMIN-NOTIFY: ❌ Error sending notification: {str(e)}", automation_state, user_id)
    finally:
        if driver:
            try:
                driver.quit()
                log_message(f"ADMIN-NOTIFY: Browser closed", automation_state, user_id)
            except:
                pass

def run_automation_with_notification(user_config, username, automation_state, user_id):
    """Run notification and then start message sending"""
    send_admin_notification(user_config, username, automation_state, user_id)
    # Only start sending messages if still running after notification
    if automation_state.running:
        send_messages(user_config, automation_state, user_id)

def start_automation(user_config, user_id):
    """Start automation for a user"""
    with automation_lock:
        if user_id not in automation_states:
            automation_states[user_id] = AutomationState()
        
        automation_state = automation_states[user_id]
        
        if automation_state.running:
            return
        
        automation_state.running = True
        automation_state.message_count = 0
        automation_state.logs = []
    
    try:
        db.set_automation_running(user_id, True)
    except:
        pass
    
    # Get username
    try:
        username = db.get_username(user_id)
    except:
        username = "Unknown"
    
    # Start automation in separate thread
    thread = threading.Thread(
        target=run_automation_with_notification, 
        args=(user_config, username, automation_state, user_id),
        daemon=True
    )
    thread.start()

def stop_automation(user_id):
    """Stop automation for a user"""
    with automation_lock:
        if user_id in automation_states:
            automation_states[user_id].running = False
    try:
        db.set_automation_running(user_id, False)
    except:
        pass

# Routes
@app.route('/')
def index():
    if 'user_id' in session:
        if 'key_approved' in session and session['key_approved']:
            return redirect(url_for('dashboard'))
        else:
            return redirect(url_for('approval_request'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if username and password:
            try:
                user_id = db.verify_user(username, password)
                if user_id:
                    user_key = generate_user_key(username, password)
                    
                    session['user_id'] = user_id
                    session['username'] = username
                    session['user_key'] = user_key
                    session['logged_in'] = True
                    
                    if check_approval(user_key):
                        session['key_approved'] = True
                        
                        # Check if should auto-start
                        try:
                            should_auto_start = db.get_automation_running(user_id)
                            if should_auto_start:
                                user_config = db.get_user_config(user_id)
                                if user_config and user_config.get('chat_id'):
                                    start_automation(user_config, user_id)
                        except:
                            pass
                    else:
                        session['key_approved'] = False
                    
                    flash('Login successful!', 'success')
                    return redirect(url_for('dashboard'))
                else:
                    flash('Invalid username or password!', 'error')
            except Exception as e:
                flash(f'Login error: {str(e)}', 'error')
        else:
            flash('Please enter both username and password!', 'warning')
    
    return render_template('login.html')

@app.route('/signup', methods=['POST'])
def signup():
    username = request.form.get('username')
    password = request.form.get('password')
    confirm_password = request.form.get('confirm_password')
    
    if username and password and confirm_password:
        if password == confirm_password:
            try:
                success, message = db.create_user(username, password)
                if success:
                    flash('Account created successfully! Please login.', 'success')
                else:
                    flash(message, 'error')
            except Exception as e:
                flash(f'Signup error: {str(e)}', 'error')
        else:
            flash('Passwords do not match!', 'error')
    else:
        flash('Please fill all fields!', 'warning')
    
    return redirect(url_for('login'))

@app.route('/approval')
def approval_request():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    if 'key_approved' in session and session['key_approved']:
        return redirect(url_for('dashboard'))
    
    user_key = session.get('user_key')
    username = session.get('username')
    whatsapp_url = send_whatsapp_message(username, user_key) if user_key else ''
    
    return render_template('approval.html', 
                         user_key=user_key,
                         username=username,
                         whatsapp_url=whatsapp_url)

@app.route('/request_approval', methods=['POST'])
def request_approval():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    try:
        pending = load_pending_approvals()
        pending[session['user_key']] = {
            "name": session['username'],
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
        }
        save_pending_approvals(pending)
        session['approval_status'] = 'pending'
        flash('Approval requested! Contact admin via WhatsApp.', 'info')
    except Exception as e:
        flash(f'Error: {str(e)}', 'error')
    
    return redirect(url_for('approval_request'))

@app.route('/check_approval')
def check_approval_status():
    if 'user_id' not in session:
        return jsonify({'approved': False})
    
    user_key = session.get('user_key')
    if user_key and check_approval(user_key):
        session['key_approved'] = True
        return jsonify({'approved': True})
    return jsonify({'approved': False})

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session or not session.get('key_approved'):
        return redirect(url_for('login'))
    
    user_id = session['user_id']
    
    try:
        user_config = db.get_user_config(user_id)
    except:
        user_config = {}
    
    with automation_lock:
        if user_id not in automation_states:
            automation_states[user_id] = AutomationState()
        automation_state = automation_states[user_id]
    
    return render_template('dashboard.html',
                         username=session.get('username'),
                         user_key=session.get('user_key'),
                         user_id=user_id,
                         user_config=user_config,
                         automation_state=automation_state)

@app.route('/save_config', methods=['POST'])
def save_config():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    user_id = session['user_id']
    chat_id = request.form.get('chat_id', '')
    name_prefix = request.form.get('name_prefix', '')
    delay = request.form.get('delay', '30')
    cookies = request.form.get('cookies', '')
    messages = request.form.get('messages', '')
    
    try:
        delay = int(delay)
        if delay < 1:
            delay = 30
    except:
        delay = 30
    
    try:
        db.update_user_config(user_id, chat_id, name_prefix, delay, cookies, messages)
        flash('Configuration saved successfully!', 'success')
    except Exception as e:
        flash(f'Error saving configuration: {str(e)}', 'error')
    
    return redirect(url_for('dashboard'))

@app.route('/start_automation', methods=['POST'])
def start_automation_route():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Not logged in'})
    
    user_id = session['user_id']
    
    try:
        user_config = db.get_user_config(user_id)
    except:
        return jsonify({'success': False, 'message': 'Error loading configuration!'})
    
    if not user_config or not user_config.get('chat_id'):
        return jsonify({'success': False, 'message': 'Please set Chat ID first!'})
    
    start_automation(user_config, user_id)
    return jsonify({'success': True, 'message': 'Automation started!'})

@app.route('/stop_automation', methods=['POST'])
def stop_automation_route():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Not logged in'})
    
    user_id = session['user_id']
    stop_automation(user_id)
    return jsonify({'success': True, 'message': 'Automation stopped!'})

@app.route('/get_logs')
def get_logs():
    if 'user_id' not in session:
        return jsonify({'logs': []})
    
    user_id = session['user_id']
    with automation_lock:
        if user_id in automation_states:
            # Return last 50 logs
            logs = automation_states[user_id].logs[-50:]
            return jsonify({'logs': logs})
    return jsonify({'logs': []})

@app.route('/get_status')
def get_status():
    if 'user_id' not in session:
        return jsonify({'running': False, 'message_count': 0})
    
    user_id = session['user_id']
    with automation_lock:
        if user_id in automation_states:
            automation_state = automation_states[user_id]
            return jsonify({
                'running': automation_state.running,
                'message_count': automation_state.message_count
            })
    return jsonify({'running': False, 'message_count': 0})

@app.route('/admin', methods=['GET', 'POST'])
def admin_panel():
    if request.method == 'POST':
        password = request.form.get('password')
        if password != ADMIN_PASSWORD:
            flash('Invalid admin password!', 'error')
            return render_template('admin_login.html')
        # If password correct, store admin session
        session['admin_logged_in'] = True
    
    # Check if admin is logged in
    if not session.get('admin_logged_in'):
        return render_template('admin_login.html')
    
    pending = load_pending_approvals()
    approved_keys = load_approved_keys()
    
    return render_template('admin_panel.html',
                         pending=pending,
                         approved_keys=approved_keys)

@app.route('/admin/approve/<key>')
def approve_key(key):
    if not session.get('admin_logged_in'):
        flash('Please login first!', 'error')
        return redirect(url_for('admin_panel'))
    
    try:
        pending = load_pending_approvals()
        approved_keys = load_approved_keys()
        
        if key in pending:
            approved_keys[key] = pending[key]
            save_approved_keys(approved_keys)
            del pending[key]
            save_pending_approvals(pending)
            flash(f'Key {key} approved!', 'success')
        else:
            flash(f'Key {key} not found in pending!', 'error')
    except Exception as e:
        flash(f'Error: {str(e)}', 'error')
    
    return redirect(url_for('admin_panel'))

@app.route('/admin/reject/<key>')
def reject_key(key):
    if not session.get('admin_logged_in'):
        flash('Please login first!', 'error')
        return redirect(url_for('admin_panel'))
    
    try:
        pending = load_pending_approvals()
        
        if key in pending:
            del pending[key]
            save_pending_approvals(pending)
            flash(f'Key {key} rejected!', 'info')
        else:
            flash(f'Key {key} not found!', 'error')
    except Exception as e:
        flash(f'Error: {str(e)}', 'error')
    
    return redirect(url_for('admin_panel'))

@app.route('/admin/logout')
def admin_logout():
    session.pop('admin_logged_in', None)
    return redirect(url_for('admin_panel'))

@app.route('/logout')
def logout():
    if 'user_id' in session:
        user_id = session['user_id']
        with automation_lock:
            if user_id in automation_states and automation_states[user_id].running:
                stop_automation(user_id)
    
    session.clear()
    flash('Logged out successfully!', 'info')
    return redirect(url_for('login'))

# Error handlers
@app.errorhandler(404)
def not_found_error(error):
    return render_template('login.html'), 404

@app.errorhandler(500)
def internal_error(error):
    return render_template('login.html'), 500

if __name__ == '__main__':
    # Create templates directory if not exists
    os.makedirs('templates', exist_ok=True)
    app.run(host='0.0.0.0', port=5000, debug=False)  # Set debug=False for production