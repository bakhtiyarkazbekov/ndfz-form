import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
import streamlit_authenticator as stauth
import pickle
import json


def app():
    # Display Title and Description
    st.title("Форма для НДФЗ")
    st.markdown("Введите данные о случаях ограничения потребления.")

    # Define the scope
    SCOPES = [
        'https://www.googleapis.com/auth/spreadsheets',
        'https://www.googleapis.com/auth/drive'
    ]

    # Load credentials from Streamlit secrets
    try:
        # Use the AttrDict directly without parsing
        service_account_info = st.secrets["GOOGLE_CREDENTIALS_PATH"]
        credentials = Credentials.from_service_account_info(service_account_info, scopes=SCOPES)
        client = gspread.authorize(credentials)
    except Exception as e:
        st.error(f"Ошибка авторизации: {e}")
        st.stop()

    # Open your Google Sheet
    SPREADSHEET_NAME = "НДФЗ-Ограничение"  # Replace with your spreadsheet name
    try:
        spreadsheet = client.open(SPREADSHEET_NAME)
        worksheet = spreadsheet.worksheet("Restrictions")
    except Exception as e:
        st.error(f"Ошибка доступа к Google Sheet: {e}")
        st.stop()

    # Function to fetch data from the sheet
    def fetch_data():
        try:
            # Fetch data from your source (e.g., Google Sheets or database)
            data = worksheet.get_all_values()
            
            # Use only the first 6 columns
            data = [row[:6] for row in data]
            
            # Create DataFrame with the first row as headers
            if data:
                df = pd.DataFrame(data[1:], columns=data[0])
            else:
                df = pd.DataFrame(columns=["ID", "Дата", "Время начала", "Время конца", "Тип", "Объем, МВт"])
            
            return df
        except Exception as e:
            st.error(f"Ошибка чтения данных: {e}")
            return pd.DataFrame(columns=["ID", "Дата", "Время начала", "Время конца", "Тип", "Объем, МВт"])


    # Function to update data in the sheet
    def update_sheet(dataframe):

        # Ensure dates are in consistent format
        if 'Дата' in dataframe.columns:
            dataframe['Дата'] = pd.to_datetime(
                dataframe['Дата'], format='%d.%m.%Y', errors='coerce', dayfirst=True
            ).dt.strftime('%Y-%m-%d')   
            
                 
        # Sort by 'Дата' and 'Время начала'
        if 'Время начала' in dataframe.columns:
            dataframe = dataframe.sort_values(by=['Дата', 'Время начала'], ascending=[True, True])

        # Replace NaN values with empty strings to ensure JSON compliance
        dataframe = dataframe.fillna("")

        worksheet.clear()
        worksheet.append_row(dataframe.columns.tolist())  # Add headers
        worksheet.append_rows(dataframe.values.tolist())  # Add rows


    # Fetch initial data
    existing_data = fetch_data()

    # Add auto-generated ID column if it doesn't exist
    if 'ID' not in existing_data.columns:
        existing_data.insert(0, 'ID', range(1, len(existing_data) + 1))

    # Form for data input
    with st.form(key="restriction_form"):
        st.markdown("### Добавить новую запись")
        date = st.date_input(label="Дата*")
        start_time = st.text_input(label="Время начала (ЧЧ:ММ)*", placeholder="12:04")
        end_time = st.text_input(label="Время конца (ЧЧ:ММ)*", placeholder="12:15")
        restriction_type = st.selectbox(
            "Тип*", 
            options=["САОН", "Команда СО"],  # Add other restriction types as needed
        )
        volume = st.number_input("Объем, МВт*", min_value=0.0, step=0.01)

        submit_button = st.form_submit_button(label="Добавить запись")

        # Form submission logic
        if submit_button:
            if not date or not start_time or not end_time or not restriction_type or volume is None:
                st.warning("Все обязательные поля должны быть заполнены.")
            else:
                # Auto-generate ID for the new record
                if not existing_data.empty:
                    existing_data['ID'] = pd.to_numeric(existing_data['ID'], errors='coerce')  # Ensure IDs are numeric
                    new_id = existing_data['ID'].max() + 1
                else:
                    new_id = 1

                new_row = [
                    new_id,
                    date.strftime("%d.%m.%Y"),
                    start_time,
                    end_time,
                    restriction_type,
                    volume,
                ]
                # Append new data to the DataFrame
                new_df = pd.DataFrame([new_row], columns=existing_data.columns)
                new_df = new_df.fillna("")  # Replace NaN values with empty strings
                existing_data = pd.concat([existing_data, new_df], ignore_index=True)
                existing_data = existing_data.fillna("")  # Ensure no NaN values before updating
                
                # Update the Google Sheet
                update_sheet(existing_data)
                existing_data = fetch_data()
                st.success("Запись успешно добавлена!")

    # Display the existing data with a refresh button
    st.markdown("### Существующие записи")
    st.dataframe(existing_data)


    # Edit/Delete Section
    st.markdown("### Изменить или удалить запись")
    selected_id = st.number_input("Введите ID записи для изменения или удаления:", min_value=1, step=1)

    # Check if the ID exists
    if selected_id in existing_data['ID'].values:
        record = existing_data[existing_data['ID'] == selected_id]
        st.write("Выбранная запись:")
        st.write(record)

        # Edit or delete options
        action = st.radio("Действие:", ["Изменить", "Удалить"])

        if action == "Изменить":
            with st.form(key="edit_form"):
                st.markdown("### Изменить запись")
                edit_date = st.date_input("Дата*", value=pd.to_datetime(record['Дата'].values[0], format="%d.%m.%Y"))
                edit_start_time = st.text_input("Время начала (ЧЧ:ММ)*", value=record['Время начала'].values[0])
                edit_end_time = st.text_input("Время конца (ЧЧ:ММ)*", value=record['Время конца'].values[0])
                edit_restriction_type = st.selectbox(
                    "Тип*", 
                    options=["САОН", "Команда СО"],
                    index=["САОН", "Команда СО"].index(record['Тип'].values[0]),
                )
                edit_volume = st.number_input(
                    "Объем, МВт*", 
                    value=float(record['Объем, МВт'].values[0]), 
                    min_value=0.0, 
                    step=0.01
                )
                update_button = st.form_submit_button("Обновить запись")

                if update_button:
                    # Update the record in the DataFrame
                    existing_data.loc[existing_data['ID'] == selected_id, ['Дата', 'Время начала', 'Время конца', 'Тип', 'Объем, МВт']] = [
                        edit_date.strftime("%d.%m.%Y"),
                        edit_start_time,
                        edit_end_time,
                        edit_restriction_type,
                        edit_volume,
                    ]
                    # Update the Google Sheet
                    update_sheet(existing_data)
                    st.success("Запись успешно обновлена!")

        elif action == "Удалить":
            if st.button("Удалить запись"):
                # Remove the record from the DataFrame
                existing_data = existing_data[existing_data['ID'] != selected_id]
                # Update the Google Sheet
                update_sheet(existing_data)
                st.success("Запись успешно удалена!")


