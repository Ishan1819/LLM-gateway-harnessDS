<#
.SYNOPSIS
  Remove the AI Cost Governor deployment (namespace "acg" only).
  Nothing outside that namespace is touched; your current kubectl context
  is not changed. Deleting the namespace also deletes the demo database.

.EXAMPLE
  .\scripts\teardown.ps1
  .\scripts\teardown.ps1 -Context kind-a7-cluster
#>
param([string]$Context = 'docker-desktop')

kubectl --context $Context delete namespace acg --ignore-not-found
