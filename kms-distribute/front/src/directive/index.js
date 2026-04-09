import hasPermi from './auth'

const install = function(app) {
  app.directive('hasPermi', hasPermi)
}

export default install
