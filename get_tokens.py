from intuitlib.client import AuthClient
from intuitlib.enums import Scopes
import yaml
import os
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse
import threading
import json

def load_credentials(file_path='credentials.yml'):
    with open(file_path, 'r') as f:
        return yaml.safe_load(f)

def save_credentials(creds, file_path='credentials.yml'):
    with open(file_path, 'w') as f:
        yaml.dump(creds, f)

class CallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        # Parse the authorization code from the callback URL
        query_components = parse_qs(urlparse(self.path).query)
        
        if 'code' in query_components:
            self.server.authorization_code = query_components['code'][0]
            
            # Send a success response
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write(b"Authorization successful! You can close this window.")
        else:
            self.send_response(400)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write(b"Authorization failed! No code received.")
        
        # Stop the server
        threading.Thread(target=self.server.shutdown).start()

def get_tokens_for_company(client_id, client_secret, environment, redirect_uri, company_id, port=5000):
    auth_client = AuthClient(
        client_id=client_id,
        client_secret=client_secret,
        environment=environment,
        redirect_uri=redirect_uri
    )
    
    # Get the authorization URL
    scopes = [
        Scopes.ACCOUNTING,
        Scopes.OPENID,
        Scopes.EMAIL,
        Scopes.PROFILE,
    ]
    auth_url = auth_client.get_authorization_url(scopes)
    
    # Start local server to handle the callback
    server = HTTPServer(('localhost', port), CallbackHandler)
    server.authorization_code = None
    server_thread = threading.Thread(target=server.serve_forever)
    server_thread.daemon = True
    server_thread.start()
    
    # Open the authorization URL in browser
    print(f"\nOpening authorization URL for company ID: {company_id}")
    print("Please login and authorize the application...")
    webbrowser.open(auth_url)
    
    # Wait for the callback
    while server_thread.is_alive():
        try:
            server_thread.join(1)
        except KeyboardInterrupt:
            server.shutdown()
            raise
    
    if not server.authorization_code:
        raise Exception("Failed to get authorization code")
    
    # Exchange the authorization code for tokens
    auth_client.get_bearer_token(server.authorization_code, realm_id=company_id)
    
    return {
        'access_token': auth_client.access_token,
        'refresh_token': auth_client.refresh_token,
        'environment': environment,
        'redirect_uri': redirect_uri,
        'company_id': company_id
    }

def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    credentials_path = os.path.join(script_dir, 'credentials.yml')
    
    # Load existing credentials
    creds = load_credentials(credentials_path)
    
    companies = {
        'source',
        'target'
    }
    
    for company_name in companies:
        print(f"\nGetting tokens for {company_name}...")
        
        # Get new tokens
        company_tokens = get_tokens_for_company(
            client_id=creds['client_id'],
            client_secret=creds['client_secret'],
            environment=creds[company_name]['environment'],
            redirect_uri=creds[company_name]['redirect_uri'],
            company_id=creds[company_name]['company_id'],
            port=5000
        )
        
        # Update credentials
        creds[company_name].update(company_tokens)
        
        print(f"Successfully obtained new tokens for {company_name}")
        
        # Save after each company in case of errors
        save_credentials(creds, credentials_path)
        print(f"Saved new tokens to {credentials_path}")

if __name__ == "__main__":
    main() 