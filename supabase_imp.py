import os
from datetime import datetime
import random
from supabase import create_client, Client
import yaml
from dataclasses import dataclass

@dataclass
class Module_M_measurement:
    created_at: str # ISO 8601 -> datetime.now().isoformat()
    millis: list[int]               # millis from module-M on every measurement, must be in ascending order. millis can however overflow to 0
    L1_amps_avg: int
    L1_amps_max: int
    L1_amps_min: int
    L2_amps_avg: int
    L2_amps_max: int
    L2_amps_min: int
    L3_amps_avg: int
    L3_amps_max: int
    L3_amps_min: int
    L1_phaseangle: list[int]        # phase angle in degrees, array must be the same length as millis
    L2_phaseangle: list[int]
    L3_phaseangle: list[int]        
    frequency: list[int]                # frequency in Hz, array must be the same length as millis
    L1_phaseshift_millis: list[int]     # module-M millis when L1 phase shift is detected, can be empty
    L2_phaseshift_millis: list[int]
    L3_phaseshift_millis: list[int]

class SupabaseImp:
    user_email = None
    user_password = None
    user_id = None

    def __init__(self):
        self.url = 'https://vvyptbixgezvsmdkhnvr.supabase.co'
        self.public_key = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InZ2eXB0Yml4Z2V6dnNtZGtobnZyIiwicm9sZSI6ImFub24iLCJpYXQiOjE3MzYyNDIxOTgsImV4cCI6MjA1MTgxODE5OH0.aePd-hIiGGH5hZnYK5viFVNo12U5p8bEqHhPEUBqsxA'
        self.get_user_data()
        self.supabase = create_client(self.url, self.public_key)
        self.sign_in()


    def get_user_data(self):
        """ Get user data from local yaml file
        create a file named user_data.yaml in the same directory as this file, with the contents:
        email: your_email
        password: your_password
        """
        with open("user_data.yaml", "r") as file:
            user_data = yaml.safe_load(file)
        # check data validity
        if not user_data:
            raise ValueError("No data found in user_data.yaml")
        if not user_data.get("email") or not user_data.get("password"):
            raise ValueError("Invalid data in user_data.yaml")
        self.user_email = user_data["email"]
        self.user_password = user_data["password"]


    def sign_in(self):
        if self.user_email is None or self.user_password is None:
            raise ValueError("User data not found")
        if not self.supabase:
            raise ValueError("Supabase client not initialized")
        response = self.supabase.auth.sign_in_with_password(
            {"email": self.user_email, "password": self.user_password}
        )
        # validate response
        if not response.user:
            raise ValueError("Invalid user data")
        if not response.user.id:
            raise ValueError("Invalid user data")
        self.user_id = response.user.id
        print("User signed in successfully")

    def insert_moduleM_measurements(self, data: list[Module_M_measurement]):
        response = self.supabase.auth.get_session()
        if not response:
            raise ValueError("User not signed in")
        data_dicts = [vars(measurement) for measurement in data]
        print(data_dicts)
        try:
            response = self.supabase.table('Module-M-measurements_5sec').insert(data_dicts).execute()
            print("\n")
            print(response)
        except Exception as e:
            print(e)


def inset_dummy_data(database: SupabaseImp):
    # Function to generate 50 elements of dummy data
    def generate_dummy_data(base, count=25):
        return [base + random.randint(0, 10) for _ in range(count)]
    
    measurements = []
    for i in range(0, 100*60, 100):
        measurements.append(Module_M_measurement(
        created_at=datetime.now().isoformat(),
        millis=generate_dummy_data(i),
        L1_amps_avg=int(i * 2.0),
        L1_amps_max=int(i * 1.9),
        L1_amps_min=int(i * 1.8),
        L2_amps_avg=int(i * 1.7),
        L2_amps_max=int(i * 1.6),
        L2_amps_min=int(i * 1.5),
        L3_amps_avg=int(i * 1.4),
        L3_amps_max=int(i * 1.3),
        L3_amps_min=int(i * 1.2),
        L1_phaseangle=generate_dummy_data(i),
        L2_phaseangle=generate_dummy_data(i),
        L3_phaseangle=generate_dummy_data(i),
        frequency=[i, i + 20, i + 30],
        L1_phaseshift_millis=[i, i + 20, i + 30],
        L2_phaseshift_millis=[],
        L3_phaseshift_millis=[i, i + 20, i + 30]
    ))
    database.insert_moduleM_measurements(measurements)       

if __name__ == "__main__":
    database = SupabaseImp()
    # inset_dummy_data(database)
