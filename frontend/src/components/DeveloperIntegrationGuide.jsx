import React, { useState, useMemo, useEffect } from 'react';
import PropTypes from 'prop-types';

// ─── Feature Catalog Data ────────────────────────────────────────────────────

const TAG_COLORS = {
  'OTEL':            { bg: '#e8f0fe', color: '#1a73e8' },
  'REST API':        { bg: '#e6f4ea', color: '#1e8e3e' },
  'LLM API':         { bg: '#fef7e0', color: '#b45309' },
  'RAG':             { bg: '#ede7ff', color: '#7b61ff' },
  'Vector Search':   { bg: '#fde8d0', color: '#e8710a' },
  'PII Detection':   { bg: '#fce8e6', color: '#d93025' },
  'Event Collector': { bg: '#e0f4fb', color: '#007ab8' },
  'Redis':           { bg: '#f1f3f4', color: '#5f6368' },
  'Azure':           { bg: '#e8f0fe', color: '#1557b0' },
  'All Types':       { bg: '#f1f3f4', color: '#202124' },
  'Common+':         { bg: '#fef7e0', color: '#92400e' },
  'High Tier':       { bg: '#fce8e6', color: '#d93025' },
  'Production Only': { bg: '#e6f4ea', color: '#1e8e3e' },
};

// CATEGORIES and FEATURES loaded from /content/*.json at runtime

// ─── Tag pill ─────────────────────────────────────────────────────────────────

function TagPill({ tag }) {
  const style = TAG_COLORS[tag] || { bg: '#f1f3f4', color: '#5f6368' };
  return (
    <span style={{
      display:'inline-flex', alignItems:'center',
      padding:'0.1rem 0.5rem', borderRadius:10,
      fontSize:'0.65rem', fontWeight:600,
      background:style.bg, color:style.color,
      marginRight:3, marginBottom:3, whiteSpace:'nowrap',
    }}>{tag}</span>
  );
}

// ─── Feature card ─────────────────────────────────────────────────────────────

const FeatureCard = React.memo(function FeatureCard({ feature, selected, onToggle, expanded, onExpand }) {
  const isSelected = selected.has(feature.id);

  return (
    <div style={{
      background: 'var(--surface)',
      border: `1.5px solid ${isSelected ? 'var(--un-blue)' : 'var(--border)'}`,
      borderRadius: 10, padding: '0.875rem',
      cursor: feature.mandatory ? 'default' : 'pointer',
      transition: 'all 0.15s',
      boxShadow: isSelected ? '0 0 0 3px rgba(0,158,219,0.12)' : 'var(--shadow-1)',
    }} onClick={() => !feature.mandatory && onToggle(feature.id)}>

      <div style={{ display:'flex', alignItems:'flex-start', gap:'0.6rem', marginBottom:'0.4rem' }}>
        <div style={{
          width:18, height:18, borderRadius:4, flexShrink:0,
          border: `2px solid ${isSelected ? 'var(--un-blue)' : 'var(--border)'}`,
          background: isSelected ? 'var(--un-blue)' : 'white',
          display:'flex', alignItems:'center', justifyContent:'center', marginTop:1,
        }}>
          {isSelected && <span style={{ color:'white', fontSize:'0.65rem', fontWeight:700 }}>✓</span>}
        </div>
        <div style={{ flex:1, minWidth:0 }}>
          <div style={{ display:'flex', alignItems:'center', gap:'0.4rem', flexWrap:'wrap' }}>
            <span style={{ fontFamily:'Syne,sans-serif', fontWeight:700, fontSize:'0.82rem' }}>
              {feature.label}
            </span>
            {feature.mandatory && (
              <span style={{ fontSize:'0.62rem', background:'var(--success-light)', color:'var(--success)', padding:'0.05rem 0.4rem', borderRadius:8, fontWeight:700 }}>
                MANDATORY
              </span>
            )}
            <span style={{ fontSize:'0.62rem', background:'var(--surface-3)', color:'var(--text-tertiary)', padding:'0.05rem 0.4rem', borderRadius:8 }}>
              {feature.id}
            </span>
          </div>
          <p style={{ fontSize:'0.75rem', color:'var(--text-secondary)', marginTop:'0.2rem', lineHeight:1.4 }}>
            {feature.desc}
          </p>
        </div>
      </div>

      <div style={{ display:'flex', flexWrap:'wrap', marginBottom:'0.4rem' }}>
        {feature.tags.map(t => <TagPill key={t} tag={t} />)}
      </div>

      <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between' }}>
        <div style={{ fontSize:'0.68rem', color:'var(--text-tertiary)' }}>
          {feature.metric && <span>📊 {feature.metric}</span>}
          {feature.unit && <span style={{ marginLeft:6 }}>· {feature.unit}</span>}
          {feature.threshold && <span style={{ marginLeft:6, color:'var(--success)', fontWeight:600 }}>· {feature.threshold}</span>}
        </div>
        <button onClick={e => { e.stopPropagation(); onExpand(feature.id); }}
          style={{ fontSize:'0.68rem', color:'var(--primary)', background:'none', border:'none', cursor:'pointer', padding:'0 0.25rem' }}>
          {expanded === feature.id ? 'Less ▲' : 'Specs ▼'}
        </button>
      </div>

      {expanded === feature.id && (
        <div style={{ marginTop:'0.75rem', paddingTop:'0.75rem', borderTop:'1px solid var(--surface-3)' }}
          onClick={e => e.stopPropagation()}>
          <div style={{ marginBottom:'0.5rem' }}>
            <div style={{ fontSize:'0.68rem', fontWeight:700, color:'var(--text-tertiary)', textTransform:'uppercase', letterSpacing:'0.06em', marginBottom:'0.2rem' }}>App Requirement</div>
            <p style={{ fontSize:'0.78rem', color:'var(--text-primary)', lineHeight:1.5 }}>{feature.appRequirement}</p>
          </div>
          <div style={{ marginBottom:'0.5rem' }}>
            <div style={{ fontSize:'0.68rem', fontWeight:700, color:'var(--text-tertiary)', textTransform:'uppercase', letterSpacing:'0.06em', marginBottom:'0.2rem' }}>Data Format</div>
            <p style={{ fontSize:'0.78rem', color:'var(--text-primary)', lineHeight:1.5 }}>{feature.dataFormat}</p>
          </div>
          <div>
            <div style={{ fontSize:'0.68rem', fontWeight:700, color:'var(--text-tertiary)', textTransform:'uppercase', letterSpacing:'0.06em', marginBottom:'0.2rem' }}>Code Snippet</div>
            <pre style={{
              fontSize:'0.72rem', background:'var(--surface-3)', padding:'0.6rem 0.75rem',
              borderRadius:6, overflowX:'auto', lineHeight:1.6,
              color:'var(--text-primary)', whiteSpace:'pre-wrap', wordBreak:'break-word',
            }}>{feature.codeHint}</pre>
          </div>
          {feature.governanceStep && (
            <div style={{ marginTop:'0.5rem', fontSize:'0.68rem', color:'var(--un-blue)' }}>
              🔗 Maps to: {feature.governanceStep}
            </div>
          )}
        </div>
      )}
    </div>
  );
});

const featureShape = PropTypes.shape({
  id: PropTypes.string.isRequired,
  cat: PropTypes.string.isRequired,
  mandatory: PropTypes.bool.isRequired,
  label: PropTypes.string.isRequired,
  desc: PropTypes.string.isRequired,
  tags: PropTypes.arrayOf(PropTypes.string).isRequired,
  channel: PropTypes.string,
  metric: PropTypes.string,
  unit: PropTypes.string,
  threshold: PropTypes.string,
  governanceStep: PropTypes.string,
  appRequirement: PropTypes.string,
  dataFormat: PropTypes.string,
  codeHint: PropTypes.string,
});

TagPill.propTypes = {
  tag: PropTypes.string.isRequired,
};

FeatureCard.propTypes = {
  feature: featureShape.isRequired,
  selected: PropTypes.instanceOf(Set).isRequired,
  onToggle: PropTypes.func.isRequired,
  expanded: PropTypes.string,
  onExpand: PropTypes.func.isRequired,
};

// ─── Main Component ───────────────────────────────────────────────────────────

export default function DeveloperIntegrationGuide() {
  const [categories, setCategories] = useState([]);
  const [features, setFeatures] = useState([]);
  const [contentLoading, setContentLoading] = useState(true);
  const [selected, setSelected] = useState(new Set());
  const [activeCategory, setActiveCategory] = useState('baseline');
  const [expanded, setExpanded] = useState(null);

  useEffect(() => {
    Promise.all([
      fetch('/content/features.json').then(r => r.json()),
      fetch('/content/categories.json').then(r => r.json()),
    ]).then(([featureData, categoryData]) => {
      setFeatures(featureData);
      setCategories(categoryData);
      setSelected(new Set(featureData.filter(f => f.mandatory).map(f => f.id)));
      setContentLoading(false);
    });
  }, []);

  const toggleFeature = (id) => {
    setSelected(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  };

  const toggleExpand = (id) => setExpanded(prev => prev === id ? null : id);

  const filtered = useMemo(() => features.filter(f => {
    const catMatch = activeCategory === 'all' || f.cat === activeCategory;
    return catMatch;
  }), [activeCategory, features]);

  const selectedCount = selected.size;
  const mandatoryCount = features.filter(f => f.mandatory).length;

  if (contentLoading) return (
    <div style={{ padding: '3rem', textAlign: 'center', color: 'var(--text-tertiary)' }}>
      Loading feature catalog…
    </div>
  );

  return (
    <div>

      {/* Stats Bar */}
      <div style={{
        display:'flex', alignItems:'center', gap:'1.5rem', flexWrap:'wrap',
        padding:'0.875rem 1.25rem', background:'var(--surface-2)',
        border:'1px solid var(--border)', borderRadius:10, marginBottom:'1.25rem',
      }}>
        {[
          { val: selectedCount, label: 'Selected', color: 'var(--un-blue)' },
          { val: features.length, label: 'Total Features', color: 'var(--text-primary)' },
          { val: mandatoryCount, label: 'Mandatory', color: 'var(--success)' },
          { val: categories.length, label: 'Categories', color: 'var(--text-primary)' },
        ].map((item, i) => (
          <div key={i} style={{ display:'flex', alignItems:'center', gap:'1.5rem' }}>
            {i > 0 && <div style={{ width:1, height:32, background:'var(--border)' }} />}
            <div style={{ textAlign:'center' }}>
              <div style={{ fontFamily:'Syne,sans-serif', fontSize:'1.5rem', fontWeight:800, color:item.color, lineHeight:1 }}>{item.val}</div>
              <div style={{ fontSize:'0.68rem', color:'var(--text-tertiary)', fontWeight:600, textTransform:'uppercase', letterSpacing:'0.06em' }}>{item.label}</div>
            </div>
          </div>
        ))}
      </div>

      {/* Filter Bar */}
      <div style={{ display:'flex', alignItems:'center', gap:'0.5rem', flexWrap:'wrap', marginBottom:'1.25rem' }}>
        <button onClick={() => setActiveCategory('all')}
          style={{
            padding:'0.35rem 0.875rem', borderRadius:20, fontSize:'0.78rem', fontWeight:600,
            border:`1.5px solid ${activeCategory === 'all' ? 'var(--un-blue)' : 'var(--border)'}`,
            background: activeCategory === 'all' ? 'var(--un-blue)' : 'var(--surface)',
            color: activeCategory === 'all' ? 'white' : 'var(--text-secondary)',
            cursor:'pointer', fontFamily:'inherit',
          }}>
          All ({features.length})
        </button>
        {categories.map(cat => {
          const count = features.filter(f => f.cat === cat.id).length;
          const isActive = activeCategory === cat.id;
          return (
            <button key={cat.id} onClick={() => setActiveCategory(cat.id)}
              style={{
                padding:'0.35rem 0.875rem', borderRadius:20, fontSize:'0.78rem', fontWeight:600,
                border:`1.5px solid ${isActive ? cat.color : 'var(--border)'}`,
                background: isActive ? cat.color : 'var(--surface)',
                color: isActive ? 'white' : 'var(--text-secondary)',
                cursor:'pointer', fontFamily:'inherit',
              }}>
              {cat.label} ({count})
            </button>
          );
        })}
      </div>

      {/* Feature Catalog grouped by category */}
      {(activeCategory === 'all' ? categories : categories.filter(c => c.id === activeCategory)).map(cat => {
        const catFeatures = filtered.filter(f => f.cat === cat.id);
        if (catFeatures.length === 0) return null;
        const catSelected = catFeatures.filter(f => selected.has(f.id)).length;

        return (
          <div key={cat.id} style={{ marginBottom:'1.5rem' }}>
            {/* Category header */}
            <div style={{
              display:'flex', alignItems:'center', justifyContent:'space-between',
              marginBottom:'0.75rem', padding:'0.5rem 0.75rem',
              background: `${cat.color}12`,
              border: `1px solid ${cat.color}40`,
              borderRadius: 8,
            }}>
              <div style={{ display:'flex', alignItems:'center', gap:'0.5rem' }}>
                <span style={{ width:10, height:10, borderRadius:'50%', background:cat.color, display:'inline-block' }} />
                <span style={{ fontFamily:'Syne,sans-serif', fontWeight:700, fontSize:'0.85rem', color: cat.color }}>
                  {cat.label}
                </span>
                {cat.mandatory && (
                  <span style={{ fontSize:'0.62rem', background:'var(--success-light)', color:'var(--success)', padding:'0.05rem 0.4rem', borderRadius:8, fontWeight:700 }}>
                    MANDATORY
                  </span>
                )}
              </div>
              <span style={{ fontSize:'0.72rem', color:'var(--text-tertiary)' }}>
                {catSelected}/{catFeatures.length} selected
              </span>
            </div>

            {/* Feature grid */}
            <div style={{ display:'grid', gridTemplateColumns:'repeat(auto-fill, minmax(320px, 1fr))', gap:'0.75rem' }}>
              {catFeatures.map(f => (
                <FeatureCard
                  key={f.id}
                  feature={f}
                  selected={selected}
                  onToggle={toggleFeature}
                  expanded={expanded}
                  onExpand={toggleExpand}
                />
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}
