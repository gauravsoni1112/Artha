import os.path
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from dotenv import load_dotenv

load_dotenv()

gmail_client_secrets = os.path.expanduser(
    os.getenv("GMAIL_CLIENT_SECRETS", "gmail_credentials.json")
)
gmail_token_path = os.path.expanduser(
    os.getenv("GMAIL_TOKEN_PATH", os.path.join(os.path.expanduser("~"), ".artha", "gmail_token.json"))
)

# Define what your app is allowed to do. 
# 'readonly' is safe for listing/reading emails.
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

def main():
    if not os.path.exists(gmail_client_secrets):
        raise FileNotFoundError(
            f"Gmail client secrets file not found: {gmail_client_secrets}"
        )

    creds = None
    # Check if token.json already exists
    if os.path.exists(gmail_token_path):
        creds = Credentials.from_authorized_user_file(gmail_token_path, SCOPES)
    
    # If there are no valid credentials, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            # This triggers the browser login window
            flow = InstalledAppFlow.from_client_secrets_file(
                gmail_client_secrets, SCOPES)
            creds = flow.run_local_server(port=0)
        
        # Save the credentials for the next run
        with open(gmail_token_path, 'w') as token:
            token.write(creds.to_json())
            
    print("Successfully generated " + gmail_token_path + "!")

if __name__ == '__main__':
    main()
