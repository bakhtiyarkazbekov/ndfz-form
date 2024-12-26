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
from datetime import datetime, timedelta
from statsmodels.tsa.arima.model import ARIMA

# st.set_page_config(layout="wide")

hide_streamlit_style = """
            <style>
            MainMenu {visibility: hidden;}
            footer {visibility: hidden;}


            /* Reduce spacing between Streamlit elements */
            .element-container {
                margin-bottom: 0rem; /* Decrease space between elements */
            }


            /* Adjust the main container to use up to 90% of the screen width */
            .block-container {
                max-width: 90%; /* Use 90% of the screen width */
                padding-top: 0rem; /* Reduce the top padding to decrease space */
                padding-left: 2rem; /* Add left padding */
                padding-right: 2rem; /* Add right padding */
                margin-left: auto; /* Center the main content */
                margin-right: auto; /* Center the main content */
            }
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
        combined_df['day'] = pd.to_datetime(combined_df['day'], errors='coerce')

        # Set default start and end dates
        end_day_default = datetime.today().date()  # Today's date
        start_day_default = (datetime.today() - timedelta(days=7)).date()  # 10 days before today

        # User input for filters in separate columns
        col1, col2, col3 = st.columns(3)

        with col1:
            st.subheader("Аналитика")
        with col2:
            start_day = st.date_input("Выберите начальную дату", value=start_day_default)
        with col3:
            end_day = st.date_input("Выберите конечную дату", value=end_day_default)

        col1, col2 = st.columns(2)
        with col1:
            st.markdown(
                "<div style='text-align: center; font-size: 16px; font-weight: bold;'>Факт данные</div>",
                unsafe_allow_html=True
            )

        with col2:
            st.markdown(
                "<div style='text-align: center; font-size: 16px; font-weight: bold;'>Прогнозные данные</div>",
                unsafe_allow_html=True
            )

        # Add a divider between the blocks
        # Custom minimal space divider
        st.markdown(
            "<hr style='border: 1px solid #ccc; margin: 5px 0;'>",
            unsafe_allow_html=True
        )

        # Convert 'start_day' and 'end_day' back to datetime for comparison
        start_day = pd.to_datetime(start_day)
        end_day = pd.to_datetime(end_day)

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
                title='Юж. Казахстан, МВт',
                labels={'day': 'День', 'МВт': 'МВт'},
                barmode='group',
                height=270,
                color_discrete_map=color_map,  # Apply custom colors
                text_auto=True  # Automatically display data labels
            )

            fig1.update_traces(hovertemplate='<b>День:</b> %{x}<br><b>МВт:</b> %{y}<br>')

            # Adjust text position and color inside columns
            fig1.update_traces(
                textposition='inside',  # Position labels inside bars
                textfont=dict(size=10, color='white')  # Set text color to white
            )

            fig1.update_layout(
                xaxis=dict(
                    tickformat='%d %b',  # Show day and month only (e.g., "03 Dec")
                ),
                margin=dict(l=5, r=5, t=5, b=1),  # Compact margins
                height=180,  # Reduced height
                font=dict(size=9),  # Smaller font for compactness
                legend_title='',
                title_font_size=14,
                legend=dict(
                    orientation="h",
                    y=1.0,
                    x=0.5,
                    xanchor="center",
                    yanchor="bottom"
                ),
            )


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
                title='Нагрузка ЖГРЭС, МВт',
                labels={'day': 'День', 'МВт': 'МВт'},
                barmode='group',
                height=270,
                text_auto=True  # Automatically display data labels
            )

            fig2.update_traces(hovertemplate='<b>День:</b> %{x}<br><b>МВт:</b> %{y}<br>')

            # Adjust text position and color inside columns
            fig2.update_traces(
                textposition='inside',  # Position labels inside bars
                textfont=dict(size=10, color='white')  # Set text color to white
            )

            fig2.update_layout(
                xaxis=dict(
                    tickformat='%d %b',  # Show day and month only (e.g., "03 Dec")
                ),
                margin=dict(l=5, r=5, t=5, b=1),
                height=180,
                font=dict(size=9),
                legend_title='',
                title_font_size=14,
                legend=dict(
                    orientation="h",
                    y=1.0,
                    x=0.5,
                    xanchor="center",
                    yanchor="bottom"
                ),
            )

            # Filter relevant columns for the weather data
            weather_data = filtered_data[['day', 'Кызылорда', 'Тараз', 'Шымкент', 'Туркестан']].dropna()

            # Calculate the average temperature across the cities
            weather_data['Средняя температура'] = weather_data[['Кызылорда', 'Тараз', 'Шымкент', 'Туркестан']].mean(axis=1)

            # Create a Plotly line chart
            fig3 = px.line(
                weather_data,
                x='day',
                y='Средняя температура',
                title='Температура Юж. Казахстана, (°C)',
                labels={'day': 'День', 'Средняя температура': 'Т (°C)'},
                height=100
            )

            # Add data labels to the chart
            fig3.update_traces(
                mode='lines+markers+text',  # Add lines, markers, and text labels
                text=weather_data['Средняя температура'].round(1),  # Display rounded temperature values as text
                textposition='top center'  # Position of the text labels
            )

            # Customize the layout for better appearance
            fig3.update_layout(
                xaxis=dict(
                    tickformat='%d %b',  # Show day and month only (e.g., "03 Dec")
                ),
                yaxis=dict(
                    automargin=True,  # Ensure enough space for Y-axis
                    range=[
                        weather_data['Средняя температура'].min() - 2,  # Add padding to minimum value
                        weather_data['Средняя температура'].max() + 2   # Add padding to maximum value
                    ]
                ),
                margin=dict(l=5, r=5, t=20, b=10),
                height=160,
                font=dict(size=9),
                title_font_size=14,
            )

            # Filter relevant columns for the chart
            activation_data = filtered_data[['day', 'Время начала', 'Время конца', 'Тип', 'Объем, МВт']]
        
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
                labels={'day': 'День', 'Объем, МВт': 'МВт'},
                color_discrete_map=color_map,  # Apply custom colors
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

                margin=dict(l=5, r=5, t=25, b=5),
                height=140,
                font=dict(size=9),
                legend_title='',
                title_font_size=14,
                legend=dict(
                    orientation="h",
                    y=1.0,
                    x=0.5,
                    xanchor="center",
                    yanchor="bottom"
                ),
                xaxis=dict(
                    # tickangle=45,  # Rotate x-axis labels for readability
                    # tickvals=activation_data['day'].unique(),
                    # ticktext=activation_data['day'].unique().astype(str),
                    tickformat='%d %b',  # Show day and month only (e.g., "03 Dec")
                ),
            )

            #################################

            # Cache forecast for Generation and Consumption
            @st.cache_data
            def compute_generation_forecast(df, steps=5):
                model_gen = ARIMA(df['fact_Южный Казахстан_Генерация(МВт)'], order=(2, 1, 2))
                model_fit_gen = model_gen.fit()
                forecast_gen = model_fit_gen.forecast(steps=steps)
                return [round(value) for value in forecast_gen]

            @st.cache_data
            def compute_consumption_forecast(df, steps=5):
                model_cons = ARIMA(df['fact_Южный Казахстан_Потребление(МВт)'], order=(2, 1, 2))
                model_fit_cons = model_cons.fit()
                forecast_cons = model_fit_cons.forecast(steps=steps)
                return [round(value) for value in forecast_cons]

            # Cache forecast for Жамбылская ГРЭС
            @st.cache_data
            def compute_grs_forecasts(df, steps=5):
                model_fact = ARIMA(df['fact_АО "Жамбылская ГРЭС"_Нагрузка'], order=(2, 1, 2))
                model_fit_fact = model_fact.fit()
                forecast_fact = model_fit_fact.forecast(steps=steps)

                model_plan = ARIMA(df['plan_АО "Жамбылская ГРЭС"_Нагрузка'], order=(2, 1, 2))
                model_fit_plan = model_plan.fit()
                forecast_plan = model_fit_plan.forecast(steps=steps)

                return [round(value) for value in forecast_fact], [round(value) for value in forecast_plan]

            # Cache weather forecast
            @st.cache_data
            def compute_average_temperature_forecast(df, forecast_days):
                weather_forecast_data = df[df['day'].isin(forecast_days)][['day', 'Кызылорда', 'Тараз', 'Шымкент', 'Туркестан']]
                weather_forecast_data['Средняя температура'] = weather_forecast_data[['Кызылорда', 'Тараз', 'Шымкент', 'Туркестан']].mean(axis=1)
                return weather_forecast_data



            # Filter the input data
            df_pred_1 = combined_df[combined_df['day'] >= pd.Timestamp('2024-07-01')][
                ['day', 'fact_Южный Казахстан_Генерация(МВт)', 'fact_Южный Казахстан_Потребление(МВт)']
            ].dropna().drop_duplicates(subset=['day'])

            forecast_days = pd.date_range(start=df_pred_1['day'].max() + pd.Timedelta(days=1), periods=5)

            # Get cached forecasts
            forecast_1 = compute_generation_forecast(df_pred_1)
            forecast_2 = compute_consumption_forecast(df_pred_1)

            forecast_data = pd.DataFrame({
                'day': list(forecast_days) * 2,  # Duplicate forecast_days to match the length of Показатель and МВт
                'Показатель': ['Генерация Юж. Казахстан (МВт)'] * 5 + ['Потребление Юж. Казахстан (МВт)'] * 5,
                'МВт': list(forecast_1) + list(forecast_2)
            })

            # Define custom colors for the categories in the legend
            color_map = {
                'Генерация Юж. Казахстан (МВт)': '#1f77b4',  # Blue
                'Потребление Юж. Казахстан (МВт)': '#ff7f0e'  # Orange
            }
            # Create the second chart (Forecasts)
            fig1b = px.bar(
                forecast_data,
                x='day',
                y='МВт',
                color='Показатель',
                title='Прогноз, МВт',
                labels={'day': 'День', 'МВт': 'МВт'},
                barmode='group',
                height=270,
                color_discrete_map=color_map,  # Apply custom colors
                text_auto=True  # Automatically display data labels
            )

            fig1b.update_traces(hovertemplate='<b>День:</b> %{x}<br><b>МВт:</b> %{y}<br>')

            # Adjust text position and color inside columns
            fig1b.update_traces(
                textposition='inside',  # Position labels inside bars
                textfont=dict(size=10, color='white')  # Set text color to white
            )

            fig1b.update_layout(
                xaxis=dict(
                    tickformat='%d %b',  # Show day and month only (e.g., "03 Dec")
                ),
                margin=dict(l=5, r=5, t=5, b=1),  # Compact margins
                height=180,  # Reduced height
                font=dict(size=9),  # Smaller font for compactness
                legend_title='',
                title_font_size=14,
                legend=dict(
                    orientation="h",
                    y=1.0,
                    x=0.5,
                    xanchor="center",
                    yanchor="bottom"
                ),
            )

            # Prepare data for Жамбылская ГРЭС
            df_pred_2 = combined_df[combined_df['day'] >= pd.Timestamp('2024-07-01')][
                ['day', 'fact_АО "Жамбылская ГРЭС"_Нагрузка', 'plan_АО "Жамбылская ГРЭС"_Нагрузка']
            ].dropna().drop_duplicates(subset=['day'])

            forecast_fact, forecast_plan = compute_grs_forecasts(df_pred_2)

            # Prepare forecast data for visualization
            forecast_days_2 = pd.date_range(start=df_pred_2['day'].max() + pd.Timedelta(days=1), periods=5)

            forecast_data_2 = pd.DataFrame({
                'day': list(forecast_days_2) * 2,
                'Показатель': ['Факт Жамбылская ГРЭС (МВт)'] * 5 + ['План Жамбылская ГРЭС (МВт)'] * 5,
                'МВт': forecast_fact + forecast_plan
            })

            # Create the second chart for Жамбылская ГРЭС forecasts
            fig2b = px.bar(
                forecast_data_2,
                x='day',
                y='МВт',
                color='Показатель',
                title='Прогноз ЖГРЭС, МВт',
                labels={'day': 'День', 'МВт': 'МВт'},
                barmode='group',
                height=270,
                text_auto=True
            )

            fig2b.update_traces(hovertemplate='<b>День:</b> %{x}<br><b>МВт:</b> %{y}<br>')

            fig2b.update_traces(
                textposition='inside',
                textfont=dict(size=10, color='white')
            )

            fig2b.update_layout(
                xaxis=dict(
                    tickformat='%d %b'
                ),
                margin=dict(l=5, r=5, t=5, b=1),
                height=180,
                font=dict(size=9),
                legend_title='',
                title_font_size=14,
                legend=dict(
                    orientation="h",
                    y=1.0,
                    x=0.5,
                    xanchor="center",
                    yanchor="bottom"
                )
            )


            # Filter combined_df for weather predictions in the forecast range
            weather_forecast_data = combined_df[
                combined_df['day'].isin(forecast_days)
            ][['day', 'Кызылорда', 'Тараз', 'Шымкент', 'Туркестан']]

            # Calculate the average temperature for each day
            weather_forecast_data['Средняя температура'] = weather_forecast_data[['Кызылорда', 'Тараз', 'Шымкент', 'Туркестан']].mean(axis=1)

            # Create a line chart for average temperature predictions
            fig3b = px.line(
                weather_forecast_data,
                x='day',
                y='Средняя температура',
                title='Температура, °C',
                labels={'day': 'День', 'Средняя температура': 'Т (°C)'},
                markers=True,  # Add markers for points
                height=270
            )

            # Customize hover information
            fig3b.update_traces(
                hovertemplate='<b>День:</b> %{x}<br><b>Средняя температура:</b> %{y} °C<br>'
            )

            # Add data labels to the chart
            fig3b.update_traces(
                mode='lines+markers+text',  # Add lines, markers, and text labels
                text=weather_forecast_data['Средняя температура'].round(1),  # Display rounded temperature values as text
                textposition='top center'  # Position of the text labels
            )

            # Customize layout
            fig3b.update_layout(
                xaxis=dict(
                    tickformat='%d %b'  # Show day and month only
                ),
                yaxis=dict(
                            automargin=True,  # Ensure enough space for Y-axis
                            range=[
                                weather_forecast_data['Средняя температура'].min() - 2,  # Add padding to minimum value
                                weather_forecast_data['Средняя температура'].max() + 2   # Add padding to maximum value
                            ]
                        ),
                margin=dict(l=5, r=5, t=25, b=10),
                height=160,  # Adjust height
                font=dict(size=9),  # Compact font
                title_font_size=14,
                legend=dict(
                    orientation="h",
                    y=1.0,
                    x=0.5,
                    xanchor="center",
                    yanchor="bottom"
                )
            )


            # Display fig2 and fig2b in two columns
            col1, col2 = st.columns(2)
            with col1:
                st.plotly_chart(fig1, use_container_width=True)
                st.plotly_chart(fig2, use_container_width=True)  # Historical chart for Жамбылская ГРЭС
                st.plotly_chart(fig3, use_container_width=True)  # Historical chart for Жамбылская ГРЭС
                st.plotly_chart(fig, use_container_width=True) # Historical chart for Жамбылская ГРЭС
            with col2:
                st.plotly_chart(fig1b, use_container_width=True)
                st.plotly_chart(fig2b, use_container_width=True)  # Forecast chart for Жамбылская ГРЭС
                st.plotly_chart(fig3b, use_container_width=True)  # Forecast chart for Жамбылская ГРЭС



            





        

elif authentication_status == False:
    st.session_state.authentication_status = False
    st.error("Имя пользователя/пароль не верны!")
elif authentication_status is None:
    st.session_state.authentication_status = None
    st.warning("Пожалуйста, введите ваше имя пользователя и пароль")
