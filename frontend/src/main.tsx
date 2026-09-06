import React from 'react';
import { createRoot } from 'react-dom/client';
import prediction from '../../contracts/examples/prediction.json';
import state from '../../contracts/examples/twin-state.json';
import event from '../../contracts/examples/clinical-event.json';
import audit from '../../contracts/examples/audit-record.json';
import './style.css';

function App() {
  return <main>
    <p className="eyebrow">RESEARCH PROTOTYPE · SYNTHETIC DATA</p>
    <h1>OncoTwin-BRCA</h1>
    <p>Shared foundation for the four-lead team.</p>
    <aside>Mock output only. No trained model or clinical interpretation. Contracts are provisional.</aside>
    <section aria-labelledby="twin"><h2 id="twin">{state.twin_id}</h2>
      <p>State version {state.state_version} · {state.data_version}</p></section>
    <div className="grid">
      <section><h2>Mock prediction</h2><p className="score">{Math.round(prediction.risk_probability * 100)}%</p>
        <p>Fixed demo value · {prediction.horizon_months} month horizon</p>
        <p>Confidence: {prediction.confidence.replaceAll('_', ' ')}</p></section>
      <section><h2>Event timeline</h2><p>{event.event_type.replaceAll('_', ' ')}</p>
        <time dateTime={event.effective_time}>{event.effective_time}</time><p>{event.event_id}</p></section>
      <section><h2>Data quality</h2><p>Missing: {state.missing_fields.join(', ')}</p>
        {state.quality_warnings.map(w => <p key={w}>{w}</p>)}</section>
      <section><h2>Model and audit</h2><p>{prediction.model_name} · {prediction.model_version}</p>
        <p>SHAP and risk trajectory are not implemented.</p><p>Audit fixture: {audit.audit_id}</p></section>
    </div>
  </main>;
}

createRoot(document.getElementById('root')!).render(<React.StrictMode><App /></React.StrictMode>);
