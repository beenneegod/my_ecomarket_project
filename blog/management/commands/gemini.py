import google.generativeai as genai
API_KEY = "AIzaSyCNqV54G4iLBGi2c431UhQvWXXJdhdTjyM" # Ваш ключ
genai.configure(api_key=API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash-latest') # или gemini-pro
response = model.generate_content("Напиши короткий стих о весне")
print(response.text)