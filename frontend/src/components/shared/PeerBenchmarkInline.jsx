import PropTypes from 'prop-types';

function fmt(value, digits = 3) {
  if (typeof value !== 'number' || Number.isNaN(value)) {
    return 'N/A';
  }
  return value.toFixed(digits);
}

function toStars(adoptionRate) {
  if (typeof adoptionRate !== 'number' || Number.isNaN(adoptionRate)) {
    return null;
  }
  if (adoptionRate >= 0.8) return '*****';
  if (adoptionRate >= 0.6) return '****-';
  if (adoptionRate >= 0.4) return '***--';
  if (adoptionRate >= 0.2) return '**---';
  return '*----';
}

function ordinalSuffix(value) {
  const n = Math.round(value);
  const ten = n % 10;
  const hundred = n % 100;
  if (ten === 1 && hundred !== 11) return `${n}st`;
  if (ten === 2 && hundred !== 12) return `${n}nd`;
  if (ten === 3 && hundred !== 13) return `${n}rd`;
  return `${n}th`;
}

export function PeerBenchmarkInline({
  value,
  unit,
  peerAvg,
  delta,
  p25,
  p75,
  percentileRank,
  adoptionCount,
  adoptionRate,
  popularityStars,
  peerCount,
}) {
  const computedDelta = typeof delta === 'number' ? delta : (
    (typeof value === 'number' && typeof peerAvg === 'number')
      ? value - peerAvg
      : null
  );
  const direction = computedDelta === null ? 'neutral' : (computedDelta > 0 ? 'positive' : (computedDelta < 0 ? 'negative' : 'neutral'));
  const deltaPrefix = direction === 'positive' ? '+' : '';
  const hasPeerData = typeof peerAvg === 'number' && typeof peerCount === 'number' && peerCount >= 3;
  const hasDistribution = hasPeerData && typeof p25 === 'number' && typeof p75 === 'number' && p75 > p25 && typeof value === 'number';

  const starText = popularityStars || toStars(adoptionRate);
  const position = hasDistribution ? Math.max(0, Math.min(1, (value - p25) / (p75 - p25))) : 0.5;

  return (
    <div className="peer-inline">
      <div className="peer-inline-top">
        <span className="peer-inline-value">{fmt(value)}{unit || ''}</span>
        {computedDelta !== null ? (
          <span className={`peer-inline-delta delta-${direction}`}>
            {direction === 'positive' ? '^ ' : direction === 'negative' ? 'v ' : ''}{deltaPrefix}{fmt(computedDelta)} vs peers
          </span>
        ) : (
          <span className="peer-inline-muted">Delta unavailable</span>
        )}
        {typeof percentileRank === 'number' ? (
          <span className="peer-inline-muted">{ordinalSuffix(percentileRank)} percentile</span>
        ) : (
          <span className="peer-inline-muted">Percentile unavailable</span>
        )}
        {(typeof adoptionCount === 'number' || starText) && (
          <span className="peer-inline-muted">
            {starText ? `${starText} ` : ''}{typeof adoptionCount === 'number' ? `${adoptionCount} apps` : 'Popularity unavailable'}
          </span>
        )}
      </div>
      {!hasPeerData ? (
        <div className="peer-inline-bottom peer-inline-muted">
          {typeof peerCount === 'number' && peerCount > 0
            ? `~ N=${peerCount} peers (min 3 for benchmark)`
            : 'No peer data yet (3 apps needed)'}
        </div>
      ) : hasDistribution ? (
        <div className="peer-inline-bottom">
          <div className="peer-inline-bar">
            <div className="peer-inline-track" />
            <div className="peer-inline-marker" style={{ left: `${position * 100}%` }} />
          </div>
          <div className="peer-inline-range">p25 {fmt(p25)} | med {fmt(peerAvg)} | p75 {fmt(p75)}</div>
        </div>
      ) : (
        <div className="peer-inline-bottom peer-inline-muted">Distribution unavailable</div>
      )}
    </div>
  );
}

PeerBenchmarkInline.propTypes = {
  value: PropTypes.number,
  unit: PropTypes.string,
  peerAvg: PropTypes.number,
  delta: PropTypes.number,
  p25: PropTypes.number,
  p75: PropTypes.number,
  percentileRank: PropTypes.number,
  adoptionCount: PropTypes.number,
  adoptionRate: PropTypes.number,
  popularityStars: PropTypes.string,
  peerCount: PropTypes.number,
};

PeerBenchmarkInline.defaultProps = {
  value: null,
  unit: '',
  peerAvg: null,
  delta: null,
  p25: null,
  p75: null,
  percentileRank: null,
  adoptionCount: null,
  adoptionRate: null,
  popularityStars: null,
  peerCount: null,
};
