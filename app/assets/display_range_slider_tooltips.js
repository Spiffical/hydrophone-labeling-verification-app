window.dccFunctions = window.dccFunctions || {};

window.dccFunctions.formatLogFrequencyHz = function (value) {
  var hz = Math.pow(10, Number(value));
  if (!isFinite(hz) || hz <= 0) {
    return "";
  }
  if (hz >= 1000) {
    return (hz / 1000).toFixed(2) + " kHz";
  }
  if (hz >= 100) {
    return hz.toFixed(0) + " Hz";
  }
  if (hz >= 10) {
    return hz.toFixed(1) + " Hz";
  }
  return hz.toFixed(2) + " Hz";
};

window.dccFunctions.formatDecibelRange = function (value) {
  var numeric = Number(value);
  if (!isFinite(numeric)) {
    return "";
  }
  return numeric.toFixed(1) + " dB/Hz";
};
