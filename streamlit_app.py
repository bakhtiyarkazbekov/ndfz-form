import pickle
from pathlib import Path
import streamlit as st
import streamlit_authenticator as stauth
from streamlit_option_menu import option_menu
import sys
import os
from main_app import app
import pandas as pd
from google.oauth2.service_account import Credentials
import gspread
import matplotlib.pyplot as plt
import plotly.express as px


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
    with st.sidebar:
        # Determine available modules based on user
        if username == 'ndfz':
            modules = ['Аналитика', 'Загрузка данных']
            icons = ['house-fill', 'activity']

        # Sidebar controls
        app_menu = option_menu(
            menu_title='Модули',
            options=modules,
            icons=icons,
            menu_icon='chat-text-fill',
            default_index=0,
            styles={
                "container": {"padding": "5!important"},
                "icon": {"font-size": "18px"},
                "nav-link": {"font-size": "15px", "text-align": "left", "margin": "0px", "--hover-color": "#D3D3D3"},
            }
        )

    st.session_state.authentication_status = True

    if app_menu == "Загрузка данных":
        app()

    if app_menu == "Аналитика":
        st.title("Аналитика для НДФЗ")

        # Define the scope
        SCOPES = [
            'https://www.googleapis.com/auth/spreadsheets',
            'https://www.googleapis.com/auth/drive'
        ]

        @st.cache_data
        def load_google_sheets_data():
            """Fetch data from Google Sheets and return as DataFrames."""
            try:
                # Load credentials from Streamlit secrets
                service_account_info = st.secrets["GOOGLE_CREDENTIALS_PATH"]
                client = gspread.service_account_from_dict(service_account_info)
                
                # Open Google Sheets
                spreadsheet = client.open("НДФЗ-Ограничение")
                restrictions = spreadsheet.worksheet("Restrictions")
                spravka = spreadsheet.worksheet("Spravka")
                pogoda = spreadsheet.worksheet("Pogoda")

                # Fetch data
                data_1 = restrictions.get_all_values()
                data_2 = spravka.get_all_values()
                data_3 = pogoda.get_all_values()

                # Convert to DataFrames
                df_1 = pd.DataFrame(data_1[1:], columns=data_1[0])
                df_2 = pd.DataFrame(data_2[1:], columns=data_2[0])
                df_3 = pd.DataFrame(data_3[1:], columns=data_3[0])
                
                return df_1, df_2, df_3

            except Exception as e:
                st.error(f"Ошибка загрузки данных: {e}")
                st.stop()

        @st.cache_data
        def process_data(df_1, df_2, df_3):
            """Process data and merge into a combined DataFrame."""
            # Convert dates
            df_1['Дата'] = pd.to_datetime(df_1['Дата'], format='%d.%m.%Y')
            df_2['day'] = pd.to_datetime(df_2['day'])
            df_3['day'] = pd.to_datetime(df_3['day'])

            # Pivot df_2
            df_2_pivot = df_2.pivot_table(
                index='day',
                columns=['object', 'type'],
                values=['plan', 'fact'],
                aggfunc='sum'
            ).reset_index()
            df_2_pivot.columns = ['_'.join(col).strip() if col[1] else col[0] for col in df_2_pivot.columns]

            # Pivot df_3
            df_3_pivot = df_3.pivot_table(
                index='day',
                columns='city',
                values='temperature_2m',
                aggfunc='sum'
            ).reset_index()

            # Select specific columns from df_1
            columns_to_select = ['Дата', 'Время начала', 'Время конца', 'Тип', 'Объем, МВт']
            df_1_selected = df_1[columns_to_select]

            # Merge data
            combined_df = df_3_pivot.merge(df_2_pivot, on='day', how='outer')\
                                    .merge(df_1_selected, left_on='day', right_on='Дата', how='outer')

            # Drop unnecessary columns and rows
            combined_df.drop(columns=['Дата'], inplace=True)
            combined_df.dropna(subset=['day'], inplace=True)

            return combined_df

        # Load and process data
        df_1, df_2, df_3 = load_google_sheets_data()
        combined_df = process_data(df_1, df_2, df_3)

        # Ensure 'day' column only shows the date
        combined_df['day'] = pd.to_datetime(combined_df['day']).dt.date

        # Convert all other columns to numeric
        columns_to_exclude = ['day', 'Время начала', 'Время конца', 'Тип']
        columns_to_convert = combined_df.columns.difference(columns_to_exclude)
        combined_df[columns_to_convert] = combined_df[columns_to_convert].apply(pd.to_numeric, errors='coerce')


        # Get the latest month in the data
        latest_month = combined_df['day'].max().month
        latest_year = combined_df['day'].max().year

        # Filter for the latest month
        latest_month_data = combined_df[(combined_df['day'].dt.month == latest_month) & 
                                        (combined_df['day'].dt.year == latest_year)]

        # Get the first and last date of the latest month
        default_start = latest_month_data['day'].min()
        default_end = latest_month_data['day'].max()

        # User input for filters
        # Create two columns for start and end date inputs
        col1, col2 = st.columns(2)

        # User input for filters in separate columns
        with col1:
            start_day = st.date_input("Выберите начальную дату", value=default_start)

        with col2:
            end_day = st.date_input("Выберите конечную дату", value=default_end)


        # Filter the data based on the selected dates
        filtered_data = combined_df[(combined_df['day'] >= start_day) & (combined_df['day'] <= end_day)]

        # Ensure filtered data is not empty
        if filtered_data.empty:
            st.warning("Нет данных для выбранного диапазона дат.")
        else:
            # First Chart: Генерация и Потребление по Южному Казахстану
            chart_data_1 = (
                filtered_data[['day', 'fact_Южный Казахстан_Генерация(МВт)', 'fact_Южный Казахстан_Потребление(МВт)']]
                .dropna()
                .drop_duplicates(subset=['day'])
            )

            # Melt the data to reshape for Plotly
            chart_data_1 = chart_data_1.melt(id_vars='day', var_name='Показатель', value_name='МВт')

            # Rename legend labels by mapping values
            chart_data_1['Показатель'] = chart_data_1['Показатель'].replace({
                'fact_Южный Казахстан_Генерация(МВт)': 'Генерация Юж. Казахстан (МВт)',
                'fact_Южный Казахстан_Потребление(МВт)': 'Потребление Юж. Казахстан (МВт)'
            })

            # Define custom colors for the categories in the legend
            color_map = {
                'Генерация Юж. Казахстан (МВт)': '#1f77b4',  # Blue
                'Потребление Юж. Казахстан (МВт)': '#ff7f0e'  # Orange
            }

            # Create the first chart
            fig1 = px.bar(
                chart_data_1,
                x='day',
                y='МВт',
                color='Показатель',
                title='Генерация и Потребление по Южному Казахстану, МВт',
                labels={'day': 'День', 'МВт': 'МВт'},
                barmode='group',
                height=600,
                color_discrete_map=color_map  # Apply custom colors
            )

            fig1.update_traces(hovertemplate='<b>День:</b> %{x}<br><b>МВт:</b> %{y}<br>')

            fig1.update_layout(
                xaxis=dict(tickangle=45),
                font=dict(size=12),
                legend_title='Показатель',
                title_font_size=16,
                legend=dict(
                    orientation="h",
                    y=1.0,
                    x=0.5,
                    xanchor="center",
                    yanchor="bottom"
                ),
            )

            # Display the first chart
            st.plotly_chart(fig1, use_container_width=True)


            # Second Chart: Нагрузка по Жамбылской ГРЭС
            chart_data_2 = (
                filtered_data[['day', 'fact_АО "Жамбылская ГРЭС"_Нагрузка', 'plan_АО "Жамбылская ГРЭС"_Нагрузка']]
                .dropna()
                .drop_duplicates(subset=['day'])
            )

            # Melt the data to reshape for Plotly
            chart_data_2 = chart_data_2.melt(id_vars='day', var_name='Показатель', value_name='МВт')

            # Rename legend labels by mapping values
            chart_data_2['Показатель'] = chart_data_2['Показатель'].replace({
                'fact_АО "Жамбылская ГРЭС"_Нагрузка': 'Факт ЖГРЭС (МВт)',
                'plan_АО "Жамбылская ГРЭС"_Нагрузка': 'План ЖГРЭС (МВт)'
            })

            # Create the second chart
            fig2 = px.bar(
                chart_data_2,
                x='day',
                y='МВт',
                color='Показатель',
                title='Нагрузка Жамбылской ГРЭС, МВт',
                labels={'day': 'День', 'МВт': 'МВт'},
                barmode='group',
                height=600,
            )

            fig2.update_traces(hovertemplate='<b>День:</b> %{x}<br><b>МВт:</b> %{y}<br>')

            fig2.update_layout(
                xaxis=dict(tickangle=45),
                font=dict(size=12),
                legend_title='Показатель',
                title_font_size=16,
                legend=dict(
                    orientation="h",
                    y=1.0,
                    x=0.5,
                    xanchor="center",
                    yanchor="bottom"
                ),
            )

            # Display the second chart
            st.plotly_chart(fig2, use_container_width=True)

            # Filter relevant columns for the weather data
            weather_data = filtered_data[['day', 'Кызылорда', 'Тараз', 'Шымкент', 'Туркестан']].dropna()

            # Calculate the average temperature across the cities
            weather_data['Средняя температура'] = weather_data[['Кызылорда', 'Тараз', 'Шымкент', 'Туркестан']].mean(axis=1)

            # Create a Plotly line chart
            fig3 = px.line(
                weather_data,
                x='day',
                y='Средняя температура',
                title='Средняя температура Юж. Казахстана, (°C)',
                labels={'day': 'День', 'Средняя температура': 'Температура (°C)'},
                height=600
            )

            # Add data labels to the chart
            fig3.update_traces(
                mode='lines+markers+text',  # Add lines, markers, and text labels
                text=weather_data['Средняя температура'].round(1),  # Display rounded temperature values as text
                textposition='top center'  # Position of the text labels
            )

            # Customize the layout for better appearance
            fig3.update_layout(
                xaxis=dict(tickangle=45),  # Rotate x-axis labels for better readability
                font=dict(size=12),
                title_font_size=16,
            )

            # Display the chart in Streamlit
            st.plotly_chart(fig3, use_container_width=True)


            # Filter relevant columns for the chart
            activation_data = combined_df[['day', 'Время начала', 'Время конца', 'Тип', 'Объем, МВт']].dropna()
     
            # Define custom colors based on 'Тип'
            color_map = {
                'САОН': 'blue',  # Replace 'Тип 1' with actual type values from your data
                'Команда СО': 'red'    # Replace 'Тип 2' with actual type values from your data
            }

            # Create a custom hover template
            activation_data['hover_text'] = (
                'Дата: ' + activation_data['day'].astype(str) + '<br>' +
                'c ' + activation_data['Время начала'] +
                ' до ' + activation_data['Время конца'] +
                ', объем: ' + activation_data['Объем, МВт'].astype(str) + ' МВт'
            )
            # Create a scatter plot
            fig = px.scatter(
                activation_data,
                x='day',
                y='Объем, МВт',
                color='Тип',
                title='История ограничений НДФЗ',
                labels={'day': 'Дата', 'Объем, МВт': 'Объем (МВт)'},
                color_discrete_map=color_map,  # Apply custom colors
                height=600
            )

            # Customize hover data
            fig.update_traces(
                mode='markers',  # Use points only
                marker=dict(size=10),  # Adjust point size
                hovertemplate='%{customdata}<extra></extra>',
                customdata=activation_data['hover_text']  # Attach custom hover text
            )


            # Add vertical lines for each unique date
            for unique_date in activation_data['day'].unique():
                fig.add_shape(
                    type="line",
                    x0=unique_date,
                    x1=unique_date,
                    y0=0,
                    y1=activation_data['Объем, МВт'].max() * 1.1,  # Extend the line slightly above the max value
                    line=dict(color="gray", width=1, dash="dot"),  # Style for vertical lines
                    xref="x",
                    yref="y"
                )

            # Customize x-axis to show only activation dates
            fig.update_layout(
                xaxis=dict(
                    tickangle=45,  # Rotate x-axis labels for readability
                    tickvals=activation_data['day'].unique(),  # Set x-axis ticks to unique activation dates
                    ticktext=activation_data['day'].unique().astype(str)  # Convert dates to strings for display
                ),
                font=dict(size=12),
                title_font_size=16,
            )

            # Display the chart in Streamlit
            st.plotly_chart(fig, use_container_width=True)





        

elif authentication_status == False:
    st.session_state.authentication_status = False
    st.error("Имя пользователя/пароль не верны!")
elif authentication_status is None:
    st.session_state.authentication_status = None
    st.warning("Пожалуйста, введите ваше имя пользователя и пароль")
