const gulp = require('gulp')
const uglify = require('gulp-uglify')
const del = require('del')
const sass = require('gulp-sass')
const filelog = require('gulp-filelog')
const include = require('gulp-include')
const colours = require('colors/safe')
const sourcemaps = require('gulp-sourcemaps')
const path = require('path')

// Paths
let environment
const repoRoot = path.join(__dirname)
const npmRoot = path.join(repoRoot, 'node_modules')
const govukFrontendRoot = path.join(npmRoot, 'govuk-frontend')
const sspContentRoot = path.join(npmRoot, 'digitalmarketplace-frameworks')
const assetsFolder = path.join(repoRoot, 'app', 'assets')
const staticFolder = path.join(repoRoot, 'app', 'static')
const govukFrontendFontsFolder = path.join(govukFrontendRoot, 'govuk', 'assets', 'fonts')
const govukFrontendImagesFolder = path.join(govukFrontendRoot, 'govuk', 'assets', 'images')

// JavaScript paths
const jsSourceFile = path.join(assetsFolder, 'javascripts', 'application.js')
const jsDistributionFolder = path.join(staticFolder, 'javascripts')
const jsDistributionFile = 'application.js'

// CSS paths
const cssSourceGlob = path.join(assetsFolder, 'scss', 'application*.scss')
const cssDistributionFolder = path.join(staticFolder, 'stylesheets')

// Legacy paths
const dmToolkitScssRoot = path.join(repoRoot, 'app', 'assets', 'scss', 'toolkit')
const dmToolkitTemplateRoot = path.join(repoRoot, 'app', 'templates', 'toolkit')
const govukCopiedScssRoot = path.join(repoRoot, 'app', 'assets', 'scss', 'govuk')

// Configuration
const sassOptions = {
  development: {
    outputStyle: 'expanded',
    lineNumbers: true,
    includePaths: [
      path.join(assetsFolder, 'scss'),
      govukFrontendRoot
    ],
    sourceComments: true,
    errLogToConsole: true
  },
  production: {
    outputStyle: 'compressed',
    lineNumbers: true,
    includePaths: [
      path.join(assetsFolder, 'scss'),
      govukFrontendRoot
    ]
  }
}

const uglifyOptions = {
  development: {
    mangle: false,
    output: {
      beautify: true,
      semicolons: true,
      comments: true,
      indent_level: 2
    },
    compress: false
  },
  production: {
    mangle: true
  }
}

const logErrorAndExit = function logErrorAndExit (err) {
  const printError = function (type, message) {
    console.log('gulp ' + colours.red('ERR! ') + type + ': ' + message)
  }

  printError('message', err.message)
  printError('file name', err.fileName)
  printError('line number', err.lineNumber)
  process.exit(1)
}

gulp.task('clean:js', function () {
  return del(jsDistributionFolder + '/**/*').then(function (paths) {
    console.log('💥  Deleted the following JavaScript files:\n', paths.join('\n'))
  })
})

gulp.task('clean:css', function () {
  return del(cssDistributionFolder + '/**/*').then(function (paths) {
    console.log('💥  Deleted the following CSS files:\n', paths.join('\n'))
  })
})

gulp.task('clean:legacy', function () {
  return del(
    [dmToolkitScssRoot, dmToolkitTemplateRoot, govukCopiedScssRoot]
  ).then(function (paths) {
    console.log('💥  Deleted the following legacy directories:\n', paths.join('\n'))
  })
})

gulp.task('clean', gulp.parallel('clean:js', 'clean:css', 'clean:legacy'))

gulp.task('sass', function () {
  const stream = gulp.src(cssSourceGlob)
    .pipe(filelog('Compressing SCSS files'))
    .pipe(
      sass(sassOptions[environment]))
    .on('error', logErrorAndExit)
    .pipe(gulp.dest(cssDistributionFolder))

  stream.on('end', function () {
    console.log('💾  Compressed CSS saved as .css files in ' + cssDistributionFolder)
  })

  return stream
})

gulp.task('js', function () {
  const stream = gulp.src(jsSourceFile)
    .pipe(filelog('Compressing JavaScript files'))
    .pipe(include({ hardFail: true }))
    .pipe(sourcemaps.init())
    .pipe(uglify(
      uglifyOptions[environment]
    ))
    .pipe(sourcemaps.write('./maps'))
    .pipe(gulp.dest(jsDistributionFolder))

  stream.on('end', function () {
    console.log('💾 Compressed JavaScript saved as ' + jsDistributionFolder + '/' + jsDistributionFile)
  })

  return stream
})

function copyFactory (resourceName, sourceFolder, targetFolder) {
  return function () {
    return gulp
      .src(sourceFolder + '/**/*', { base: sourceFolder })
      .pipe(gulp.dest(targetFolder))
      .on('end', function () {
        console.log('📂  Copied ' + resourceName)
      })
  }
}

gulp.task(
  'copy:images',
  copyFactory(
    'image assets from app to static folder',
    path.join(assetsFolder, 'images'),
    path.join(staticFolder, 'images')
  )
)

gulp.task(
  'copy:frameworks',
  copyFactory(
    'frameworks YAML into app folder',
    path.join(sspContentRoot, 'frameworks'), 'app/content/frameworks'
  )
)

gulp.task(
  'copy:govuk_frontend_assets:fonts',
  copyFactory(
    'fonts from the GOV.UK frontend assets',
    govukFrontendFontsFolder,
    path.join(staticFolder, 'fonts')
  )
)

gulp.task(
  'copy:govuk_frontend_assets:images',
  copyFactory(
    'images from GOV.UK frontend assets',
    govukFrontendImagesFolder,
    path.join(staticFolder, 'images')
  )
)

gulp.task('set_environment_to_development', function (cb) {
  environment = 'development'
  cb()
})

gulp.task('set_environment_to_production', function (cb) {
  environment = 'production'
  cb()
})

gulp.task(
  'copy',
  gulp.parallel(
    'copy:frameworks',
    'copy:images',
    'copy:govuk_frontend_assets:fonts',
    'copy:govuk_frontend_assets:images',
  )
)

gulp.task('compile', gulp.series('copy', gulp.parallel('sass', 'js')))

gulp.task('build:development', gulp.series(gulp.parallel('set_environment_to_development', 'clean'), 'compile'))

gulp.task('build:production', gulp.series(gulp.parallel('set_environment_to_production', 'clean'), 'compile'))

gulp.task('watch', gulp.series('build:development', function () {
  const jsWatcher = gulp.watch([assetsFolder + '/**/*.js'], ['js'])
  const cssWatcher = gulp.watch([assetsFolder + '/**/*.scss'], ['sass'])
  const dmWatcher = gulp.watch([npmRoot + '/digitalmarketplace-frameworks/**'], ['copy:frameworks'])
  const notice = function (event) {
    console.log('File ' + event.path + ' was ' + event.type + ' running tasks...')
  }

  cssWatcher.on('change', notice)
  jsWatcher.on('change', notice)
  dmWatcher.on('change', notice)
}))
