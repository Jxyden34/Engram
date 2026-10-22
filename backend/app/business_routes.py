"""Only Commercial builds import business implementation code."""
from fastapi import APIRouter
from app.edition import get_edition

if get_edition()=='commercial':
    from app.commercial.routes import router
else:
    router=APIRouter(prefix='/api/v1')

    @router.get('/branding')
    def branding():
        return {'name':'Engram','tagline':'private cognition layer','accent':'#b6ff4a','logo':''}

    @router.get('/setup/status')
    def setup_status():
        return {'available':False}
