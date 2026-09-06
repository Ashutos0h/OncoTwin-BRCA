from fastapi import FastAPI

app = FastAPI(title='OncoTwin-BRCA research API', version='0.1.0')

@app.get('/health')
def health():
    return {'status': 'ok', 'service': 'oncotwin-backend', 'mode': 'scaffold'}
