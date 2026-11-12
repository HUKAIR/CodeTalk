/* Preserve the selected project for every request and sibling-page link. */
function apiPath(path) {
  var project = new URLSearchParams(location.search).get("project");
  var url = new URL(path, document.baseURI || location.href);
  if (project) url.searchParams.set("project", project);
  return url.pathname + url.search + url.hash;
}
function projectPayload(payload) {
  var project = new URLSearchParams(location.search).get("project");
  if (project) payload.project = project;
  return payload;
}
document.addEventListener("DOMContentLoaded", function () {
  document.querySelectorAll('a[href^="/"]').forEach(function (link) {
    var path = link.getAttribute("href");
    if (path.indexOf("//") !== 0) link.setAttribute("href", apiPath(path));
  });
});
