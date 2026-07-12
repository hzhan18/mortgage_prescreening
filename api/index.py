from app import app
from vercel_wsgi import VercelWSGI

handler = VercelWSGI(app)
