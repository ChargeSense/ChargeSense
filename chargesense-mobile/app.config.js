const { expo } = require('./app.json');
module.exports = () => ({
  ...expo,
  android: {
    ...expo.android,
    ...(process.env.GOOGLE_SERVICES_JSON ? { googleServicesFile: process.env.GOOGLE_SERVICES_JSON } : {}),
  },
  extra: {
    ...expo.extra,
    ...(process.env.EXPO_PUBLIC_EAS_PROJECT_ID
      ? { eas: { projectId: process.env.EXPO_PUBLIC_EAS_PROJECT_ID } } : {}),
  },
});
