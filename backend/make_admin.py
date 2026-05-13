import firebase_admin
from firebase_admin import credentials, auth
import sys

def make_admin(email):
    try:
        # Initialize Firebase Admin if not already initialized
        try:
            firebase_admin.get_app()
        except ValueError:
            cred = credentials.Certificate("serviceAccountKey.json")
            firebase_admin.initialize_app(cred)

        # Get the user by email
        user = auth.get_user_by_email(email)
        
        # Set the custom admin claims
        current_claims = user.custom_claims or {}
        current_claims['admin'] = True
        current_claims['role'] = 'admin'
        
        auth.set_custom_user_claims(user.uid, current_claims)
        
        print(f"✅ Successfully granted admin privileges to: {email}")
        print(f"UID: {user.uid}")
        print("They can now log into the Admin Dashboard.")
        
    except auth.UserNotFoundError:
        print(f"❌ Error: No user found with email '{email}'.")
        print("Please create an account for them in the Firebase Auth console first, or sign up via the app.")
    except Exception as e:
        print(f"❌ An error occurred: {e}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python make_admin.py <email>")
        sys.exit(1)
        
    email_address = sys.argv[1]
    make_admin(email_address)
