import pickle
from pathlib import Path
import streamlit as st
import streamlit_authenticator as stauth
from streamlit_option_menu import option_menu
import sys
import os
from main_app import app


hide_streamlit_style = """
            <style>
            MainMenu {visibility: hidden;}
            footer {visibility: hidden;}
            </style>
            """
st.markdown(hide_streamlit_style, unsafe_allow_html=True)

# Add the parser_module directory to the Python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), 'parser_module')))


# Use a fixed secret key (store it securely in a real application)
secret_key = "abcde"  # Use a fixed secret key; replace with a secure method in production

# Define user credentials
names = ["NDFZ",]
usernames = ['ndfz']

# Load hashed passwords
file_path = Path(__file__).parent / "hashed_pw.pkl"
if file_path.exists():
    with file_path.open("rb") as file:
        try:
            hashed_passwords = pickle.load(file)
        except (EOFError, pickle.UnpicklingError) as e:
            st.error("Error loading password file.")
            st.stop()
else:
    st.error("Password file not found.")
    st.stop()

# Initialize the authenticator
authenticator = stauth.Authenticate(
    names,
    usernames,
    hashed_passwords,
    "dashboard",
    secret_key,
    0  # cookie_expiry_days
)

# Define function to clear session state
def clear_session_state():
    for key in list(st.session_state.keys()):
        del st.session_state[key]

# Check if user is authenticated
if 'authentication_status' not in st.session_state:
    st.session_state.authentication_status = None

name, authentication_status, username = authenticator.login("Login", "main")

if authentication_status:
    app()

elif authentication_status == False:
    st.session_state.authentication_status = False
    st.error("Имя пользователя/пароль не верны!")
elif authentication_status is None:
    st.session_state.authentication_status = None
    st.warning("Пожалуйста, введите ваше имя пользователя и пароль")
