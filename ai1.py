import tkinter as tk
from tkinter import ttk, scrolledtext
import ttkbootstrap as tb
import threading, queue, os, subprocess, time, webbrowser, requests
import speech_recognition as sr
import pyttsx3
import smtplib, ssl
from email.mime.text import MIMEText
import pywhatkit as kit  # YouTube support
import google.generativeai as genai  # Gemini AI

# --- Queues for Thread-Safe Communication ---
ui_queue = queue.Queue()
command_queue = queue.Queue()

# --- User Configuration ---

# 1. Contacts for Email
contacts = {
    "talal": "talal.ahmad@example.com", # Replace with actual name and email
    "friend": "friend.email@example.com",
    # Add more contacts here
}

# 2. Country codes for NewsAPI
country_codes = {
    "united states": "us", "usa": "us", "america": "us",
    "pakistan": "pk",
    "india": "in",
    "united kingdom": "gb", "uk": "gb",
    "australia": "au",
    "canada": "ca",
    "germany": "de",
    "france": "fr",
}


# --- Speech Engine ---
try:
    engine = pyttsx3.init()
    engine.setProperty("rate", 170)
    engine.setProperty("volume", 1)
except Exception as e:
    print(f"Failed to initialize pyttsx3: {e}")
    def speak(text):
        print(f"SPEAK (TTS disabled): {text}")
        ui_queue.put({"action": "chat_reply", "text": text})
else:
    def speak(text):
        ui_queue.put({"action": "speaking", "state": True})
        engine.say(text)
        engine.runAndWait()
        ui_queue.put({"action": "chat_reply", "text": text})
        ui_queue.put({"action": "speaking", "state": False})

# --- Helper function for interactive commands ---
def listen_for_response(timeout=7):
    """Listens for a single response from the user."""
    r = sr.Recognizer()
    mic = sr.Microphone()
    with mic as source:
        r.adjust_for_ambient_noise(source, duration=0.5)
        ui_queue.put({"action": "listening", "state": True})
        try:
            audio = r.listen(source, timeout=timeout, phrase_time_limit=10)
            text = r.recognize_google(audio).lower()
            ui_queue.put({"action": "chat_input", "text": text})
            return text
        except (sr.UnknownValueError, sr.WaitTimeoutError):
            return None
        finally:
            ui_queue.put({"action": "listening", "state": False})

# --- Email ---
def send_email_interactive():
    speak("Who is the recipient?")
    recipient_name = listen_for_response()
    if not recipient_name or recipient_name not in contacts:
        speak("Sorry, I couldn't find that contact.")
        return

    recipient_email = contacts[recipient_name]
    speak("What should be the subject of the email?")
    subject = listen_for_response()
    if not subject:
        speak("I didn't catch the subject. Cancelling email.")
        return

    speak("And what is the message?")
    message = listen_for_response()
    if not message:
        speak("I didn't catch the message. Cancelling email.")
        return

    speak(f"Sending email to {recipient_name} with subject {subject}. Please wait.")
    try:
        # <<< IMPORTANT: SET YOUR EMAIL AND GMAIL APP PASSWORD HERE >>>
        EMAIL_ADDRESS = "yor own email"
        EMAIL_PASSWORD = "in app password"

        msg = MIMEText(message)
        msg["Subject"] = subject
        msg["From"] = EMAIL_ADDRESS
        msg["To"] = recipient_email

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
            server.send_message(msg)
        speak(f"Email sent successfully to {recipient_name}!")
    except Exception as e:
        speak(f"Sorry, I failed to send the email. Error: {str(e)}")


# --- Weather and News ---
def get_location():
    try:
        response = requests.get("http://ip-api.com/json/")
        data = response.json()
        return data.get("city", "Unknown")
    except:
        return "Unknown"

def get_weather(city):
    # <<< IMPORTANT: SET YOUR OPENWEATHERMAP API KEY HERE >>>
    OPENWEATHER_API_KEY = "Your-API-KEY"
    try:
        url = f"http://api.openweathermap.org/data/2.5/weather?q={city}&appid={OPENWEATHER_API_KEY}&units=metric"
        response = requests.get(url)
        data = response.json()
        if data["cod"] == 200:
            temp = data["main"]["temp"]
            desc = data["weather"][0]["description"]
            return f"The weather in {city} is {desc} with a temperature of {temp}°C."
        else:
            return f"Sorry, I couldn't find weather information for {city}."
    except:
        return "Sorry, I couldn't fetch the weather information."

def get_news(country_code='us'):
    # <<< IMPORTANT: SET YOUR NEWSAPI KEY HERE >>>
    NEWS_API_KEY = "Your-API-KEY"
    try:
        url = f"https://newsapi.org/v2/top-headlines?country={country_code}&apiKey={NEWS_API_KEY}"
        response = requests.get(url)
        data = response.json()
        if data["status"] == "ok" and data["articles"]:
            headlines = [article["title"] for article in data["articles"][:5]]
            return "Here are the top headlines: " + " | ".join(headlines)
        else:
            return "Sorry, I couldn't fetch the news."
    except:
        return "Sorry, I couldn't fetch the news."

# --- AI General Query Handler (Gemini) ---
def ask_ai(question):
    # <<< IMPORTANT: SET YOUR GEMINI API KEY HERE >>>
    GEMINI_API_KEY = "Your-API-Key"
    genai.configure(api_key=GEMINI_API_KEY)
    try:
        model = genai.GenerativeModel("gemini-1.5-flash")
        response = model.generate_content(question)
        return response.text
    except Exception as e:
        return f"Sorry, I'm having trouble connecting to Gemini. Error: {str(e)}"

# --- Listening & Processing ---
def process_command(text):
    ui_queue.put({"action": "chat_input", "text": text})
    ui_queue.put({"action": "thinking"})
    if not handle_command(text):
        ai_response = ask_ai(text)
        speak(ai_response)

def listen_and_process():
    r = sr.Recognizer()
    mic = sr.Microphone()
    with mic as source:
        r.adjust_for_ambient_noise(source)
    speak("Hello Talal, Twisto is ready.")

    while True:
        # Check for manual text input first
        try:
            manual_command = command_queue.get_nowait()
            process_command(manual_command)
            continue
        except queue.Empty:
            pass

        # Listen for voice command
        with mic as source:
            try:
                ui_queue.put({"action": "listening", "state": True})
                audio = r.listen(source, timeout=5, phrase_time_limit=7)
                text = r.recognize_google(audio).lower()
                process_command(text)
            except (sr.UnknownValueError, sr.WaitTimeoutError):
                ui_queue.put({"action": "listening", "state": False})
                continue

# --- Commands ---
def handle_command(text_low):
    # --- Interactive Commands ---
    if "send an email" in text_low or "send email" in text_low:
        send_email_interactive()
        return True

    if "weather" in text_low:
        words = text_low.split()
        if "in" in words:
            try:
                city_index = words.index("in") + 1
                if city_index < len(words):
                    city = ' '.join(words[city_index:])
                    speak(get_weather(city))
                    return True
            except ValueError:
                pass # "in" not found, fall through
        # Fallback to current location
        speak(get_weather(get_location()))
        return True

    if "news" in text_low:
        for country_name, code in country_codes.items():
            if country_name in text_low:
                speak(get_news(code))
                return True
        # Fallback to default
        speak(get_news())
        return True

    # --- Standard Commands ---
    if "hello" in text_low or "hi" in text_low:
        speak("Hi Talal, how can I help you?")
        return True

    if "open notepad" in text_low:
        speak("Opening Notepad")
        subprocess.Popen(["notepad.exe"])
        return True

    if "open chrome" in text_low:
        speak("Opening Google Chrome")
        try:
            chrome_path = "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"
            subprocess.Popen([chrome_path])
        except FileNotFoundError:
            speak("Chrome is not installed in a default path.")
        return True
    
    # <<< NEW COMMAND ADDED HERE >>>
    if "open youtube" in text_low:
        speak("Opening YouTube")
        webbrowser.open("https://www.youtube.com")
        return True
        
    if "play on youtube" in text_low or ("youtube" in text_low and "play" in text_low):
        query = text_low.replace("play on youtube", "").replace("youtube", "").replace("play", "").strip()
        if query:
            speak(f"Playing {query} on YouTube")
            kit.playonyt(query)
        else:
            speak("What should I play on YouTube?")
        return True

    if "time" in text_low:
        current_time = time.strftime("%I:%M %p")
        speak(f"The current time is {current_time}")
        return True

    if "date" in text_low:
        current_date = time.strftime("%B %d, %Y")
        speak(f"Today's date is {current_date}")
        return True

    if "quit twisto" in text_low or "exit program" in text_low:
        speak("Goodbye Talal!")
        ui_queue.put({"action": "quit_app"})
        return True

    return False

# --- GUI ---
class TwistoApp(tb.Window):
    def __init__(self):
        super().__init__(themename="cyborg")
        self.title("Twisto AI Assistant")
        self.geometry("650x800")
        self.minsize(550, 700)

        self.configure(bg="#2c3e50")

        # --- Animation State Variables (No files needed!) ---
        self.is_pulsing = False
        self.pulse_radius = 40
        self.min_radius = 38
        self.max_radius = 45
        self.pulse_direction = 1

        # --- Main Layout ---
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # Header Frame
        header = ttk.Frame(self, style='TFrame', padding=(20, 10))
        header.grid(row=0, column=0, sticky='ew')
        header.columnconfigure(0, weight=1)

        self.status_label = ttk.Label(header, text="Initializing...", font=("Segoe UI", 12, "italic"), style='Status.TLabel')
        self.status_label.grid(row=0, column=0, sticky='w')

        # Canvas for the animated indicator
        self.mic_canvas = tk.Canvas(self, width=120, height=120, bg="#2c3e50", highlightthickness=0)
        self.mic_canvas.place(relx=0.5, y=100, anchor='center')
        
        # Draw the initial circle
        self.indicator_circle = self.mic_canvas.create_oval(
            60-self.pulse_radius, 60-self.pulse_radius,
            60+self.pulse_radius, 60+self.pulse_radius,
            fill="#3498db", outline=""
        )

        # Chat Frame
        chat_container = ttk.Frame(self, padding=20)
        chat_container.grid(row=1, column=0, sticky='nsew', pady=(80, 0))
        chat_container.grid_rowconfigure(0, weight=1)
        chat_container.grid_columnconfigure(0, weight=1)

        self.chat_area = scrolledtext.ScrolledText(chat_container, wrap=tk.WORD, state="disabled", relief="flat",
                                                  bg="#2c3e50", fg="#ecf0f1", font=("Segoe UI", 11), bd=0)
        self.chat_area.grid(row=0, column=0, sticky="nsew")

        # --- CORRECTED Tag Styles for Chat Bubbles ---
        self.chat_area.tag_config("user_frame", justify="right")
        self.chat_area.tag_config("user", background="#3498db", foreground="white", relief="raised", borderwidth=2,
                                  lmargin1=80, lmargin2=80, rmargin=10, spacing3=10, wrap="word",
                                  font=("Segoe UI", 11, "bold"))

        self.chat_area.tag_config("twisto_frame", justify="left")
        self.chat_area.tag_config("twisto", background="#34495e", foreground="white", relief="raised", borderwidth=2,
                                  lmargin1=10, lmargin2=10, rmargin=80, spacing3=10, wrap="word")

        # Input Frame
        input_frame = ttk.Frame(self, padding=(20, 10, 20, 20))
        input_frame.grid(row=2, column=0, sticky='ew')
        input_frame.columnconfigure(0, weight=1)

        self.entry = tb.Entry(input_frame, font=("Segoe UI", 12))
        self.entry.grid(row=0, column=0, sticky='ew', ipady=8)
        self.entry.bind("<Return>", self.send_manual_input)

        send_button = tb.Button(input_frame, text="Send", command=self.send_manual_input, style='success')
        send_button.grid(row=0, column=1, sticky='e', padx=(10, 0))

        self.after(100, self.process_ui_queue)

    def animate_indicator(self):
        if self.is_pulsing:
            if self.pulse_radius >= self.max_radius or self.pulse_radius <= self.min_radius:
                self.pulse_direction *= -1
            
            self.pulse_radius += self.pulse_direction * 0.3
            
            # Update circle coordinates
            self.mic_canvas.coords(self.indicator_circle,
                60-self.pulse_radius, 60-self.pulse_radius,
                60+self.pulse_radius, 60+self.pulse_radius
            )
            self.after(30, self.animate_indicator)

    def send_manual_input(self, event=None):
        text = self.entry.get().strip()
        if text:
            command_queue.put(text)
            self.entry.delete(0, "end")

    def add_message(self, message, tag):
        self.chat_area.config(state="normal")
        if self.chat_area.index('end-1c') != '1.0': self.chat_area.insert("end", "\n\n")
        
        if tag == 'user':
            self.chat_area.insert("end", f" {message} \n", ("user", "user_frame"))
        else:
            self.chat_area.insert("end", f" {message} \n", ("twisto", "twisto_frame"))

        self.chat_area.config(state="disabled")
        self.chat_area.yview_moveto(1.0)

    def process_ui_queue(self):
        while not ui_queue.empty():
            task = ui_queue.get()
            action = task.get("action")
            
            if action == "chat_input": self.add_message(task['text'], "user")
            elif action == "chat_reply": self.add_message(task['text'], "twisto")
            
            elif action == "listening":
                if task["state"]:
                    self.status_label.config(text="Listening...")
                    self.mic_canvas.itemconfig(self.indicator_circle, fill="#2ecc71") # Green
                    if not self.is_pulsing:
                        self.is_pulsing = True
                        self.animate_indicator()
                else:
                    self.is_pulsing = False
                    self.status_label.config(text="Ready")
                    self.mic_canvas.itemconfig(self.indicator_circle, fill="#3498db") # Blue
            
            elif action == "thinking":
                self.is_pulsing = False
                self.status_label.config(text="Thinking...")
                self.mic_canvas.itemconfig(self.indicator_circle, fill="#f1c40f") # Yellow

            elif action == "speaking":
                 self.is_pulsing = False
                 if task["state"]:
                     self.status_label.config(text="Speaking...")
                     self.mic_canvas.itemconfig(self.indicator_circle, fill="#e67e22") # Orange
                 else:
                     self.status_label.config(text="Ready")
                     self.mic_canvas.itemconfig(self.indicator_circle, fill="#3498db") # Blue

            elif action == "quit_app":
                self.destroy()
                os._exit(0)
        
        self.after(100, self.process_ui_queue)

# --- Main ---
def main():
    app = TwistoApp()
    threading.Thread(target=listen_and_process, daemon=True).start()
    app.mainloop()

if __name__ == "__main__":

    main()
